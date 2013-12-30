#!/usr/bin/python
'''
Created on Dec 30, 2013

@author: juan
'''

from client import Client
import txtorcon

c= Client(80, '212.183.241.237', 3, 10, 100, '/home/juan/src/tor-measure/Measures/temp')
c.join()
