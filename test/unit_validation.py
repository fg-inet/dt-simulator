""" Basic simulator validation against back-of-the-envelope test cases """

import unittest
import sys, os
import math
import logging

sys.path.insert(0,'../src')
from simulator.transferManager import TransferManager
from simulator.transfer import Transfer
from simulator.interface import Interface
from simulator.policy import *
from simulator.globals import *

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logging.disable(logging.INFO)

class TestSynthetic(unittest.TestCase):

    def ftime_simple(self, size, rtt, bandwidth):
        MSS = 1460
        remaining = size;
        time = 0
        ws = 10
        while ((ws * MSS) / rtt < bandwidth / ms(1000)) and (remaining - ws*MSS > 0):
            
            remaining -= ws * MSS
            time += rtt
            ws *= 2

        # delay = (MSS / bandwidth) * ms(1000)
        # time += delay

        if (remaining > 0):
            time += (remaining / bandwidth) * ms(1000)

        return time


    #@unittest.skip("")
    def test_1trans_if1(self):
  
        bw = mbit(8)
        size0 = mb(1)
        rtt = ms(20)
        
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2")) 


        """ Add transfers """
        t0 = Transfer( size=size0, origin="example.com", ssl=False)
        manager.addTransfer(t0)
        manager.enableTransfer(t0)


        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))

        
        """ check resulting times """
        self.assertGreater(time, (size0 / (bw * ms(1000))) + 2*rtt)
        self.assertAlmostEqual(time, 2*rtt + self.ftime_simple(size0, rtt, bw), delta=rtt)


    #@unittest.skip("")
    def test_2trans_parallel_if1(self):
  
        bw = mbit(8)
        size0 = mb(1)
        sizen = kb(200)
        ntrans = 2
        rtt = ms(20)
        
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2"))

        """ Add transfers """
        transfers = [Transfer( size=size0, origin="example.com", ssl=False)]

        for n in range(ntrans):
            tn = Transfer( size=sizen, origin="acme{n}.com".format(n=n), ssl=False) 
            transfers.append(tn)
            transfers[0].addChild(tn)

        manager.addTransfers(transfers)
        manager.enableTransfer(transfers[0])


        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))
        
        
        """ check resulting times """
        self.assertGreater(time, (size0 + sizen*ntrans)/(bw*ms(1000)) + 4*rtt)
        self.assertAlmostEqual(time, 2*rtt + self.ftime_simple(size0, rtt, bw) + 
                                     2*rtt + self.ftime_simple(sizen, rtt, bw*1.0/ntrans), delta=rtt)

    #@unittest.skip("")
    def test_ntrans_parallel_if1(self):
  
        bw = mbit(8)
        size0 = mb(1)
        sizen = kb(200)
        ntrans = 14
        rtt = ms(20)

        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2"))

        """ Add transfers """
        transfers = [Transfer( size=size0, origin="example.com", ssl=False)]

        for n in range(ntrans):
            tn = Transfer( size=sizen, origin="acme{n}.com".format(n=n), ssl=False) 
            transfers.append(tn)
            transfers[0].addChild(tn)

        manager.addTransfers(transfers)
        manager.enableTransfer(transfers[0])


        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))

        
        """ check resulting times """
        self.assertGreater(time, (size0 + sizen*ntrans)/(bw*ms(1000)) + 4*rtt)
        self.assertAlmostEqual(time, 2*rtt + self.ftime_simple(size0, rtt, bw) + 
                                         2*rtt + self.ftime_simple(sizen, rtt, bw*1.0/ntrans), delta=rtt)



       
    #@unittest.skip("")
    def test_2trans_pipeline_if1(self):
   
        bw = mbit(8)
        size0 = mb(1)
        sizen = kb(200)
        ntrans = 2
        rtt = ms(20)
   
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2"))

        """ Add transfers """
        transfers = [  Transfer( size=size0, origin="example.com", ssl=False) ]
        for n in range(1, ntrans+1): 
            tn = Transfer( size=sizen, origin="acme.com", ssl=False)
            transfers.append(tn)
            transfers[n-1].addChild(tn)

        manager.addTransfers(transfers)
        manager.enableTransfer(transfers[0])

  
        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))


        """ check resulting times """   
        T0 = 2*rtt + self.ftime_simple(size0, rtt, bw)
        Tn = 2*rtt + self.ftime_simple(ntrans*sizen, rtt, bw)
        self.assertGreater(time, (size0 + sizen*ntrans)/(bw*ms(1000)) + 4*rtt)
        self.assertAlmostEqual(time, T0 + Tn, delta=rtt)


    #@unittest.skip("")
    def test_3trans_pipeline_continue_slowstart_if1(self):
   
        bw = mbit(8)
        size0 = mb(1)
        size1 = kb(10)
        size2 = kb(200)
        rtt = ms(20)
   
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2")) 
  
        """ Add transfers """
        t0 = Transfer( size=size0, origin="example.com", ssl=False)
        t1 = Transfer( size=size1, origin="acme.com", ssl=False)        
        t2 = Transfer( size=size2, origin="acme.com", ssl=False)
        
        t0.addChild(t1)
        manager.addTransfer(t0)
        t1.addChild(t2)
        manager.addTransfer(t1)
        manager.addTransfer(t2)

        manager.enableTransfer(t0)

  
        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))

   
        """ check resulting times """
        T0 = 2*rtt + self.ftime_simple(size0, rtt, bw)
        Tn = 2*rtt + self.ftime_simple(size1+size2, rtt, bw)
        self.assertGreater(time, (size0 + size1 + size2)/(bw*ms(1000)) + 4*rtt)
        self.assertAlmostEqual(time, T0 + Tn, delta=rtt)
  

    #@unittest.skip("")
    def test_3trans_nopipeline_if1(self):

        bw = mbit(8)
        size0 = mb(1)
        size1 = mb(200)
        size2 = kb(20)
        rtt = ms(20)
   
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2")) 

  
        """ Add transfers """
        t0 = Transfer( size=size0, origin="example.com", ssl=False)
        t1 = Transfer( size=size1, origin="acme.com", ssl=False)
        t2 = Transfer( size=size2, origin="acme.com", ssl=False)
        
        t0.addChild(t1)
        t0.addChild(t2)
        manager.addTransfer(t0)
        manager.addTransfer(t1)
        manager.addTransfer(t2)

        manager.enableTransfer(t0)
        
  
        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))


        """ check resulting times """
        T0 = 2*rtt + self.ftime_simple(size0, rtt, bw)
        T2 = 2*rtt + self.ftime_simple(size2, rtt, bw/2)
        self.assertGreater(time, (size0 + size1 + size2)/(bw*ms(1000)) + 4*rtt)
        self.assertAlmostEqual(result.transfers[2].getTimes()['finishTime'], T0 + T2, delta=rtt)
    

    #@unittest.skip("")
    def test_nparallel_pipeline_if1(self):
   
        bw = mbit(8)
        size0 = mb(1)
        sizen = kb(200)
        ptrans = 50
        ntrans = 5
        rtt = ms(20)
        
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2"))

        """ Add transfers """
        transfers = [  Transfer( size=size0, origin="example.com", ssl=False) ]

        for n in range(1, ntrans+1):
            for p in range(1, ptrans+1):
                tn = Transfer( size=sizen, origin="acme{n}.com".format(n=n), ssl=False) 
                transfers[0].addChild(tn)
                transfers.insert(n*p, tn)

        manager.addTransfers(transfers)
        manager.enableTransfer(transfers[0])


        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))

        
        """ check resulting times """
        self.assertGreater(time, (size0 + sizen*ntrans)/(bw*ms(1000)) + 4*rtt)
        self.assertAlmostEqual(time, 2*rtt + self.ftime_simple(size0, rtt, bw) + 
                                         2*rtt + self.ftime_simple(sizen*ptrans, rtt, bw*1.0/ntrans), delta=rtt)


    #@unittest.skip("")
    def test_ntrans_mixpipeline_if1(self):
   
        bw = mbit(8)
        size0 = mb(1)
        size1 = mb(200)
        sizen = mb(2)
        sizem = kb(200)
        ntrans = 100
        mtransf = 5
        
        rtt = ms(20)
   
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if1"))
        interfaces.append(Interface(rtt=rtt, bandwidth=bw, description="if2")) 
  
        """ Add transfers """
        t0 = Transfer( size=size0, origin="example.com", ssl=False)
        t1 = Transfer( size=size1, origin="acme.com", ssl=False)
        t0.addChild(t1)
        transfers = [t0, t1]

        tn = t0
        for n in range(2, ntrans+2): 
           tm = tn
           tnNew = Transfer( size=sizen, origin="acme.com", ssl=False)
           tn.addChild(tnNew)
           tn = tnNew
           transfers.append(tn)

           for m in range(1, mtransf+1): 
               tmNew = Transfer( size=sizem, origin="acme.com", ssl=False)
               tm.addChild(tmNew)
               tm = tmNew
               transfers.append(tm)  

        manager.addTransfers(transfers)  
        manager.enableTransfer(transfers[0])  
  

        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, useOneInterfaceOnly(interfaces[0]))

   
        """ check resulting times """
        T0 = 2*rtt + self.ftime_simple(size0, rtt, bw)
        T1_u = 2*rtt + self.ftime_simple(size1, rtt, bw/2)
        T1_l = 2*rtt + self.ftime_simple(size1, rtt, bw/3)

        # print("\ntime: {0}".format(time))
        # print("T0: {0}".format(T0))
        # print("T1_u: {0}".format(T1_u))
        # print("T1_l: {0}".format(T1_l))
        
        self.assertGreater(time, (size0 + size1 + sizen*ntrans + sizem*ntrans*mtransf)/(bw*ms(1000)) + 4*rtt)
        self.assertGreater(time, T0 + T1_u)
        self.assertLess(time, T0 + T1_l)   
    
    
    #@unittest.skip("")
    def test_ntrans_mixpipeline_eaf(self):
   
        size0 = mb(1)
        size1 = mb(200)
        sizen = mb(2)
        sizem = kb(200)
        ntrans = 100
        mtransf = 5
        
        bw1 = mbit(8)
        bw2 = mbit(18)
        rtt1 = ms(10)
        rtt2 = ms(500)
           
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt1, bandwidth=bw1, description="if1"))
        interfaces.append(Interface(rtt=rtt2, bandwidth=bw2, description="if2"))  
  

        """ Add transfers """
        t0 = Transfer( size=size0, origin="example.com", ssl=False)
        t1 = Transfer( size=size1, origin="acme.com", ssl=False)
        t0.addChild(t1)
        transfers = [t0, t1]

        tn = t0
        for n in range(2, ntrans+2): 
           tm = tn
           tnNew = Transfer( size=sizen, origin="acme.com", ssl=False)
           tn.addChild(tnNew)
           tn = tnNew
           transfers.append(tn)

           for m in range(1, mtransf+1): 
               tmNew = Transfer( size=sizem, origin="acme.com", ssl=False)
               tm.addChild(tmNew)
               tm = tmNew
               transfers.append(tm)      
  
        manager.addTransfers(transfers)  
        manager.enableTransfer(transfers[0])        

   
        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, earliestArrivalFirst())
     

        """ check resulting times """
        T0 = 2*rtt1 + self.ftime_simple(size0, rtt1, bw1)
        T1_u = 2*rtt2 + self.ftime_simple(size1, rtt2, (bw1+bw2)/2)
        T1_l = 2*rtt1 + self.ftime_simple(size1, rtt1, (bw1+bw2)/3)

        # print("\ntime: {0}".format(time))
        # print("T0: {0}".format(T0))
        # print("T1_u: {0}".format(T1_u))
        # print("T1_l: {0}".format(T1_l))

        self.assertGreater(time, (size0 + size1 + sizen*ntrans + sizem*ntrans*mtransf)/((bw1+bw2)*ms(1000)) + 4*rtt2)
        self.assertGreater(time, T0 + T1_u)
        self.assertLess(time, T0 + T1_l) 

        
    #@unittest.skip("")
    def test_ntrans_mixpipeline_eafmptcp(self):
   
        size0 = mb(1)
        size1 = mb(200)
        sizen = kb(20)
        sizem = kb(1)
        ntrans = 100
        mtransf = 5
        
        bw1 = mbit(8)
        bw2 = mbit(18)
        rtt1 = ms(10)
        rtt2 = ms(500)
           
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt1, bandwidth=bw1, description="if1"))
        interfaces.append(Interface(rtt=rtt2, bandwidth=bw2, description="if2"))  
   
  
        """ Add transfers """
        t0 = Transfer( size=size0, origin="example.com", ssl=False)
        t1 = Transfer( size=size1, origin="acme.com", ssl=False)
        t0.addChild(t1)
        transfers = [t0, t1]
        tn = t0
        for n in range(2, ntrans+2): 
           tm = tn
           tnNew = Transfer( size=sizen, origin="acme.com", ssl=False)
           tn.addChild(tnNew)
           tn = tnNew
           transfers.append(tn)

           for m in range(1, mtransf+1): 
               tmNew = Transfer( size=sizem, origin="acme.com", ssl=False)
               tm.addChild(tmNew)
               tm = tmNew
               transfers.append(tm) 

        manager.addTransfers(transfers)  
        manager.enableTransfer(transfers[0])     

  
        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, earliestArrivalFirstMPTCP())
     

        """ check resulting times """

        self.assertGreater(time, (size0 + size1 + sizen*ntrans + sizem*ntrans*mtransf)/((bw1+bw2)*ms(1000)) + 4*rtt2)
        
        
    #@unittest.skip("")
    def test_2trans_MPTCP(self):
   
        bw1 = mbit(8)
        bw2 = mbit(18)
        rtt1 = ms(10)
        rtt2 = ms(500)
        size0 = kb(1)
        size1 = mb(200)
        
   
        """ Set up simulator """
        manager = TransferManager()

        interfaces = []
        interfaces.append(Interface(rtt=rtt1, bandwidth=bw1, description="if1"))
        interfaces.append(Interface(rtt=rtt2, bandwidth=bw2, description="if2"))  

  
        """ Add transfers """
        t0 = Transfer( size=size0, origin="acme.com", ssl=False)
        t1 = Transfer( size=size1, origin="acme.com", ssl=False)
        t0.addChild(t1)
        transfers = [t0, t1]

        manager.addTransfers(transfers)  
        manager.enableTransfer(transfers[0]) 
        
  
        """ Run the Simulator """
        (result, time) = manager.runTransfers(interfaces, earliestArrivalFirstMPTCP())
     

        """ check resulting times """
        T0   = 2*rtt1 + self.ftime_simple(size0, rtt1, bw1)
        T1   = 2*rtt2 + self.ftime_simple(size1, rtt1, bw1+bw2)
        T1_1 = 2*rtt1 + self.ftime_simple(size1, rtt1, bw1)
        T1_2 = 2*rtt2 + self.ftime_simple(size1, rtt2, bw1)

        self.assertGreater(time, (size0 + size1)/((bw1+bw2)*ms(1000)) + 4*rtt1)
        self.assertLess(time, T0 + T1_1)
        self.assertLess(time, T0 + T1_2)        
        # self.assertAlmostEqual(t1.finish_time, T0 + T1, delta=math.sqrt(rtt1*rtt1+rtt2*rtt2))



if __name__ == '__main__':
    unittest.main()
