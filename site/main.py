#!/usr/bin/env python


import wsgiref.handlers
import oauth

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.api import urlfetch

from django.utils import simplejson as json

class MainHandler(webapp.RequestHandler):
    """Demo Twitter App."""

    def get(self):

        client = oauth.OAuthClient('twitter', self)
        
        if 'unauthorized' in self.request.query_string:
            unauthorized = True
            message = "<span style='color: red;'>Your account needs to be authorized to use Twitter Hooks.</span>"
        else:
            unauthorized = False
            message = ''
        
        if client.get_cookie() and unauthorized == False:
            return self.redirect('/account')
                    
        
        self.response.out.write(template.render('templates/main.html', {'message':message}))

class DataHandler(webapp.RequestHandler):
    def get(self):
        data = {}
        for account in Account.all():
            if account.update_event:
                data[str(account.user_id)] = account.hook_url
        self.response.out.write(json.dumps(data))

class AccountHandler(webapp.RequestHandler):
    def get(self):
        account, twitter_account, client = self._get_account()
        if not twitter_account:
            return
        if not 47035435 in client.get('/friends/ids'):
            client.expire_cookie()
            self.redirect('/?unauthorized')
            return
        if not account:
            account = Account.create(twitter_account)
        message = ""
        bad_status = self.request.GET.get('badurl')
        if bad_status:
            message = "This URL returned %s. It needs to return a 2xx status code." % bad_status
        if 'success' in  self.request.query_string:
            message = "Hook settings saved!"
        self.response.out.write(template.render('templates/account.html', {'info': twitter_account, 'account':account, 'message': message}))
    
    def post(self):
        account, twitter_account, client = self._get_account()
        if not twitter_account:
            return
        url = self.request.POST.get('url', None)
        if url:
            res = urlfetch.fetch(url)
            if res.status_code < 200 or res.status_code > 299:
                self.redirect('/account?badurl=%s' % res.status_code)
                return
        if account:
            old_url = account.hook_url
            old_event = account.update_event
            account.hook_url = url
            account.update_event = bool(self.request.POST.get('update_event', False))
            account.put()
            if old_url != account.hook_url or old_event != account.update_event:
                self._update_transformer(account)
        self.redirect('/account?success')
    
    def _get_account(self):
        client = oauth.OAuthClient('twitter', self)
        if not client.get_cookie():
            self.redirect('/')
            return
        twitter_account = client.get('/account/verify_credentials')
        account = Account.all().filter('user_id =', twitter_account['id']).get()
        return (account, twitter_account, client)
    
    def _update_transformer(self, account):
        if account.update_event:
            url = account.hook_url
        else:
            url = None
        urlfetch.fetch('http://localhost:9333/', payload=json.dumps([str(account.user_id), url]), method='POST')

class Account(db.Model):
    user_id = db.IntegerProperty(required=True)
    user_screen_name = db.StringProperty(required=True)
    hook_url = db.StringProperty(default='')
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    update_event = db.BooleanProperty(default=True)
    
    @classmethod
    def create(cls, twitter_account):
        a = Account(user_id = twitter_account['id'], user_screen_name= twitter_account['screen_name'])
        a.put()
        return a

def main():
  application = webapp.WSGIApplication([('/', MainHandler), ('/account', AccountHandler), ('/data', DataHandler)],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()