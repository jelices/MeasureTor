#!/usr/bin/python
'''
Created on Dec 30, 2013

@author: juan
'''

from client import Client
import sys
import re
import urllib
import os
import random
from pkg_resources import get_distribution
from threading import Thread, Event
from multiprocessing import Queue
from argparse import ArgumentParser

from stem.connection import connect_port
from stem.descriptor import parse_file
from stem.descriptor.remote import DescriptorDownloader
from stem import ControllerError, CircStatus, StreamStatus
from stem.control import EventType

class torController(Thread):
    def __init__(self, controller, num_hops, num_circuits, num_samples, time_sample, file_prefix, port=80):
        Thread.__init__(self)
        self.ip=self.get_external_ip()
        self._controller=controller;
        self._num_hops = num_hops
        self._num_circuits = num_circuits
        self._num_samples = num_samples
        self._time_sample = time_sample
        self._file_prefix = file_prefix
        self._port = port
        self._or = {}
        self._exit_or = set()
        self._relayBW = {}
        self._paths={}
        self._streams={}
        self.circuitsCreated=0
        self._circs = {}
        self._circuits_created = Event()
        self.queue = Queue() 
        self.start()
        
    def run(self):
        self._controller.add_event_listener(self._circuit_event, EventType.CIRC)
        self.get_or_consensus()
        self.create_circuits()
        self._controller.add_event_listener(self._stream_event, EventType.STREAM)
        c= Client(self._port, self.ip, self._num_circuits, self._num_samples, self._time_sample, self._file_prefix, self.queue)
        c.join()
    
    def _circuit_event(self, event):
        if event.status == CircStatus.BUILT:
            self.circuitsCreated+=1
            self._circs.setdefault(False,[]).append(event.id);
            if self.circuitsCreated== self._num_circuits:
                self._circuits_created.set()
        elif event.status == CircStatus.CLOSED:
            self.circuitsCreated-=1
            if self._circs[False].count(event.id)>0:
                self._circs[False].remove(event.id)
            else:
                self._circs[True].remove(event.id)
            self.create_circuit()
        elif event.status == CircStatus.FAILED:
            self.create_circuit()
    
    def _stream_event(self, event):
        if event.status == StreamStatus.NEW:
            circId = self._circs[False].pop()
            self._controller.attach_stream(event.id, circId)
            self._circs.setdefault(True,[]).append(circId)
            self._streams[event.id]= event.source_port;
        elif event.status == StreamStatus.DETACHED:
            if len(self._circs[False])>0:
                circId = self._circs[False].pop()
                self._controller.attach_stream(event.id, circId)
                self._circs.setdefault(True,[]).append(circId)
            else:
                self.create_circuits()
        elif event.status == StreamStatus.SUCCEEDED:
            self._num_circuits -= 1
            self.queue.put([self._streams[event.id], self._circuit_description(self._paths[event.circ_id])])
                
    def create_circuits(self):
        for i in range(self._num_circuits+3):
            self.create_circuit()
        self._circuits_created.wait()
        self._circuits_created.clear()
        
    def get_external_ip(self):
        try:
            site = urllib.urlopen("http://www.google.com/search?q=ip").read()
            grab = re.findall('\d{2,3}.\d{2,3}.\d{2,3}.\d{2,3}', site)
            address = grab[0]
            return address
        except Exception:
            pass
        
    def _circuit_description(self,path):
        circ =[]
        for OR in path:
            circ.append(self._or[str(OR)])
            circ.append(self._relayBW[str(OR)])     
        return circ
    
    def get_or_consensus(self):
        self._or = {}
        self._relayBW = {}
        self._exit_or = set()
        data_dir = self._controller.get_conf("DataDirectory")
        try:
            for desc in parse_file(os.path.join(data_dir, 'cached-descriptors')):
                self._or[desc.fingerprint] = desc.nickname   
                self._relayBW [desc.fingerprint]= desc.observed_bandwidth
                if desc.exit_policy.can_exit_to(address=self.ip, port=self._port) and self._num_hops>1:
                    self._exit_or.add(desc.fingerprint)
                if desc.exit_policy.can_exit_to(address=self.ip, port=self._port) and self._num_hops==1 and desc.allow_single_hop_exits:
                    self._exit_or.add(desc.fingerprint)
        except Exception as exc:
            self.get_or_from_network()
    
    def get_or_from_network(self):
        self._or = {}
        self._relayBW = {}
        self._exit_or = set()
        downloader = DescriptorDownloader()
        try:
            for desc in downloader.get_server_descriptors().run():
                self._or[desc.fingerprint] = desc.nickname   
                self._relayBW [desc.fingerprint]= desc.observed_bandwidth
                if desc.exit_policy.is_exiting_allowed() and self._num_hops>1:
                    self._exit_or.add(desc.fingerprint)
                if desc.exit_policy.is_exiting_allowed() and self._num_hops==1 and desc.allow_single_hop_exits:
                    self._exit_or.add(desc.fingerprint)
        except Exception as exc:
            print "Unable to retrieve the server descriptors: %s" % exc

    def create_circuit(self):
        circId = None
        while not circId:
            path=[]
            for i in range(self._num_hops-1):
                node=random.choice(self._or.keys())
                path.append(node)
            node = random.sample(self._exit_or,1)
            path.extend(node)
            try:
                circId=self._controller.new_circuit(path)
            except ControllerError:
                print "Not able to create a circit", path
                pass
            except Exception:
                return;
        self._paths[circId]=path        
    
def main():
    assert get_distribution('stem').version > '1.0.1', 'Stem module version must be higher then 1.0.1.'
    parser = ArgumentParser(description="Probe RTTs of Tor circuits.")
    parser.add_argument("--circuits", type=int, default=10, help="Number of circuits to probe.")
    parser.add_argument("--samples", type=int, default=10, help="Number of samples taken for each circuit.")
    parser.add_argument("--time", type=int, default=1800, help="Milliseconds between measures.")
    parser.add_argument("--output", type=str, default='/home/juan/src/tor-measure/Measures/temp', help="Prefix for output files.")
    parser.add_argument("--hops", type=int, default='2', help="Number of hops.")
    parser.add_argument("--port", type=int, default='80', help="Listening port of the server.")
    parser.add_argument("--auth", type=str, default="juan", help="Authenticate password for control Tor")
    args = parser.parse_args()
    controller = connect_port()
    if not controller:
        sys.stderr.write("ERROR: Couldn't connect to Tor.\n")
        sys.exit(1)
    if not controller.is_authenticated():
        controller.authenticate(args.auth)
    try:
        controller.set_conf("UseMicrodescriptors", "0")    
        controller.set_conf("__DisablePredictedCircuits", "1")
        controller.set_conf("__LeaveStreamsUnattached", "1")

        #Close previous circuits
        for circ in controller.get_circuits():
            if not circ.build_flags or 'IS_INTERNAL' not in circ.build_flags:
                controller.close_circuit(circ.id)
        manager = torController(controller, args.hops, args.circuits, args.samples, args.time, args.output, args.port)
        manager.join()
    finally:
        controller.reset_conf("__DisablePredictedCircuits")
        controller.reset_conf("__LeaveStreamsUnattached")
        controller.reset_conf("MaxCircuitDirtiness")
        controller.close()

if __name__ == '__main__':
    main()
