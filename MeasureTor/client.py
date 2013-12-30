#!/usr/bin/python
'''
Created on Dec 30, 2013

@author: Juan Antonio Elices
'''

from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor, task, endpoints
from socksclient import SOCKSWrapper
import json
import datetime, calendar
from argparse import ArgumentParser
from multiprocessing import Process

total = 0

class clProtocol(LineReceiver):
    def __init__(self,num_requests, time_interval, file_name, num_circuits=1):
        self._num_requests = num_requests
        self._time_interval = time_interval
        self.file = open(file_name, 'w')
        self.timer = task.LoopingCall(self.sendRequest)
        self.send = 0
        self.received = 0        
        self._num_circuits = num_circuits
        
    def connectionMade(self):
        self.timer.start(self._time_interval/1000.0)
    
    def lineReceived(self, line):
        global total
        data = json.loads(line)
        data['3'] = datetime.datetime.now()
        del data['4']
        json.dump(data, self.file , cls = MyEncoder, sort_keys=True)
        self.file.write('\n')
        self.received+=1
        if self.received == self._num_requests:
            self.file.close()
            print self.transport.getHost().port
            self.transport.loseConnection()
            total += 1
            if total == self._num_circuits:
                reactor.stop()
            
    def sendRequest(self):
        if self.send < self._num_requests:
            data = {'1': datetime.datetime.now()}
            self.sendLine(json.dumps(data, cls = MyEncoder))
            self.send += 1
        else:
            self.timer.stop()
            
class clFactory(ClientFactory):

    def __init__(self, num_requests, time_interval, file_prefix, num_circuits):        
        self._num_requests = num_requests
        self._time_interval = time_interval
        self._file_prefix = file_prefix
        self._request = 0
        self._num_circuits= num_circuits

    def buildProtocol(self, addr):
        c = clProtocol(self._num_requests, self._time_interval, self._file_prefix + str(self._request)+".txt", self._num_circuits)
        self._request += 1
        return c

    def clientConnectionLost(self, connector, reason):
        reactor.stop()

class MyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
           return int(calendar.timegm(obj.timetuple()) * 1000 + obj.microsecond / 1000)       
        return json.JSONEncoder.default(self, obj)

class Client(Process):
    def __init__(self, port, ip, num_circuits, num_measures, time_interval, file_prefix):
        Process.__init__(self)
        self.factory = clFactory(num_measures, time_interval, file_prefix, num_circuits)
        endpoint = endpoints.TCP4ClientEndpoint(reactor, ip, port)
        self.s = SOCKSWrapper(reactor, 'localhost', 9050, endpoint)
        self.num_circuits=num_circuits
        self.start()
        
    def run(self):
        Process.run(self)
        for i in range(self.num_circuits):
            self.s.connect(self.factory)
        reactor.run()