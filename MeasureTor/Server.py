'''
Created on Dec 30, 2013

@author: juan
'''
from twisted.internet.protocol import Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
import json
import datetime, calendar
import random
import string
from argparse import ArgumentParser

class ServerProtocol(LineReceiver):

    def __init__(self, size):
        self.size = size-49 if size > 49 else 0
    def connectionMade(self):
        print self.transport.getPeer
    
    def lineReceived(self, line):
        data = json.loads(line)
        data['2'] = datetime.datetime.now()
        data['4'] = ''.join(random.choice(string.lowercase) for x in range(self._size))
        self.sendLine(json.dumps(data, cls = MyEncoder))
        
class ServerFactory(Factory):

    def __init__(self,size):
        self.size = size # maps user names to Chat instances

    def buildProtocol(self, addr):
        return ServerProtocol(self.size)

def main():
    parser = ArgumentParser(description="Probe RTTs of Tor circuits.")
    parser.add_argument("--size", type=int, default=50, help="Size of each response (min: 49 bytes).")
    parser.add_argument("--port", type=int, default=80, help="Listening Port")
    args = parser.parse_args()
    reactor.listenTCP(args.port, ServerFactory(args.size))
    reactor.run()


class MyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
           return int(calendar.timegm(obj.timetuple()) * 1000 + obj.microsecond / 1000)       
        return json.JSONEncoder.default(self, obj)
