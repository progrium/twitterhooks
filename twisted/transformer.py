from twisted.web.http import HTTPClient
from twisted.web.client import HTTPClientFactory
from twisted.web import server, resource, error, http
from twisted.application import internet, service
from twisted.internet import reactor
import base64
import simplejson as json
from twisted.web import client
import urllib, time, getpass

USERNAME = 'twithooks'

class TwitterStream(HTTPClient):
    stream = 0
    
    def lineReceived(self, line):
        if not self.stream:
            if line == "":
                self.stream = 1
        else:
            def parse_tweet(line, callback):
                try:
                    tweet = json.loads(line)
                    callback(tweet)
                except ValueError, e:
                    pass
            reactor.callLater(0, parse_tweet, line, self.factory.callback)
        
    def connectionMade(self):
        self.sendCommand('GET', self.factory.path)
        self.sendHeader('Authorization', 'Basic %s' % self.factory.auth)
        self.sendHeader('User-Agent', self.factory.agent)
        self.endHeaders()
        print "Connected and receiving..."

class TwitterStreamFactory(HTTPClientFactory):
    protocol = TwitterStream
    
    def __init__(self, user, password, callback, stream_type='spritzer', agent='TwitterHooks', query_params=None):
        url = 'http://stream.twitter.com/%s.json' % stream_type
        if query_params:
            url = '%s?%s' % (url, urllib.urlencode(query_params))
        self.auth = base64.b64encode('%s:%s' % (user, password))
        self.callback = callback
        self.last_retry = 0
        HTTPClientFactory.__init__(self, url=url, agent=agent)
    
    def startedConnecting(self, connector):
        self.connector = connector
        
    def clientConnectionLost(self, connector, reason):
        def retry(connector, factory):
            print "Connection lost. Retrying..."
            factory.last_retry = time.time()
            connector.connect()
        reactor.callLater(0 if (time.time() - self.last_retry) > 5 else 3, retry, connector, self)
        

class UpdateEndpoint(resource.Resource):
    isLeaf = True
    
    def __init__(self, service):
        self.service = service
    
    def render_POST(self, request):
        mapping = json.loads(request.content.getvalue())
        self.service.updateHookMapping(*mapping)
        return "OK"


class TwitterHookService(service.Service):
    hook_mapping = {'47035435': None}
    
    def __init__(self, username, password, mapping):
        self.username = username
        self.password = password
        print mapping
        self.hook_mapping.update(mapping)
    
    def getUpdateEndpointFactory(self):
        return server.Site(UpdateEndpoint(self))
    
    def getTwitterStreamFactory(self):
        f = TwitterStreamFactory(self.username, self.password, stream_type='follow', query_params={'follow': ','.join(self.hook_mapping.keys())}, callback=self.handleTweet)
        self.stream = f
        return f
    
    def handleTweet(self, tweet):
        user_id = str(tweet['user']['id'])
        if user_id in self.hook_mapping:
            post_tweet(tweet, self.hook_mapping[user_id])
        print repr(tweet)
            
    
    def updateHookMapping(self, id, url):
        if url:
            self.hook_mapping[id] = url
        else:
            if id in self.hook_mapping:
                del self.hook_mapping[id]
        self.stream.setURL('http://stream.twitter.com/follow.json?follow=%s' % ','.join(self.hook_mapping.keys()))
        self.stream.connector.disconnect()

def if_fail(reason):
    if reason.getErrorMessage()[0:3] in ['301', '302', '303']:
        return

def post_tweet(tweet, url):
    tweet['user_id'] = tweet['user']['id']
    tweet['user_screen_name'] = tweet['user']['screen_name']
    del tweet['user']
    tweet['_url'] = url
    postdata = urllib.urlencode(tweet)
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': str(len(postdata)),
    }
    client.getPage('http://hookah.webhooks.org/', followRedirect=0, method='POST', headers=headers, postdata=postdata).addErrback(if_fail)


print "Enter password for %s:" % USERNAME
passwd = getpass.getpass()
s = TwitterHookService(USERNAME, passwd, json.loads(urllib.urlopen('http://www.twitterhooks.com/data').read()))
application = service.Application('twitterhooks')
serviceCollection = service.IServiceCollection(application)
internet.TCPServer(9333, s.getUpdateEndpointFactory()).setServiceParent(serviceCollection)
internet.TCPClient('stream.twitter.com', 80, s.getTwitterStreamFactory()).setServiceParent(serviceCollection)
