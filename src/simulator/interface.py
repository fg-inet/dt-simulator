""" class to model interface parameters 

main use is to tell connections the bandwidth share they will get to progress transfers
"""

from copy import copy
from simulator.globals import toMB, bwUnit
from simulator.eventSimulator import logAdapter, NOPREDICT

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logAdapter.setup("interface")

class Interface(object):

    def __init__(self, rtt, bandwidth, description):
        assert rtt > 0
        assert bandwidth > 0
        assert len(description) > 0

        self.rtt = rtt
        self.bandwidth = bandwidth
        self.rStorage = Interface.InterfaceStorage()
        self.pStorage = None
        self.pRun = NOPREDICT
        self.description = description


    class InterfaceStorage(object):
        def __init__(self):
            self.connections = []

        def clone(self):
            clone = copy(self)
            clone.connections = self.connections[:]
            return clone

    def _storageSwitch(self, pRun):
        if self.pRun != pRun:
            self.pStorage = self.rStorage.clone()
            self.pRun = pRun

        if pRun == NOPREDICT:
            return self.rStorage
        else:
            return self.pStorage


    def reset(self):
        self.rStorage = Interface.InterfaceStorage()
        self.pStorage = None
        self.pRun = NOPREDICT


    def getRTT(self):
        return self.rtt


    def addConnection(self, connection, pRun):
        storage = self._storageSwitch(pRun)
        assert not connection in storage.connections
        storage.connections.append(connection)


    def removeConnection(self, connection, pRun):
        storage = self._storageSwitch(pRun)
        storage.connections.remove(connection)


    def getConnections(self, pRun=NOPREDICT):
        storage = self._storageSwitch(pRun)
        return storage.connections


    def updateConnectionBwShare(self, time, pRun):
        storage = self._storageSwitch(pRun)
        if not storage.connections:
            #logger.debug("updating {iface} bandwidth shares: no connections".format(iface=self.description))
            return

        #logger.debug("updating {iface} bandwidth shares".format(iface=self.description))

        # make sure we have no negative bw connctions
        assert not [ c for c in storage.connections if c.getDesiredBw(time, pRun) < 0 ]
        # list of idle connections
        connIDLE = [ c for c in storage.connections if c.getDesiredBw(time, pRun) == 0 ]
        # list of bandwidth-limited connections (congestions avoidence or late slow-strat)
        connBWB = [ c for c in storage.connections if c.getDesiredBw(time, pRun) > 0 ]
        # list of low bandwidth connections (early late slow-strat)
        connLBW = []

        # set available bandwidth for all idle connctions
        #logger.debug("found {count} idle connctions".format(count=len(connIDLE)))
        for c in connIDLE:
            c.setAvailableBw(0, time, pRun)
        
        # iterate over all badwith-limited connctions and re-classify as 
        # low bandwidth if neccessary - break once the calculation converges
        bwLowSum = 0
        bwShare = 0
        round = 0
        maxRounds = len(storage.connections)
        while connBWB and bwShare != int( (self.bandwidth - bwLowSum) / len(connBWB) ):
            assert maxRounds > round
            assert bwShare >= 0
            bwShare = int( (self.bandwidth - bwLowSum) / len(connBWB) )
            #logger.debug("calculation round {round} - bwShare={bwShare} bwLowSum={bwLowSum}".format(round=round, bwShare=bwUnit(bwShare), bwLowSum=bwUnit(bwLowSum)))
            for c in connBWB:
                # check if desired bandwidth dropped below the bwshare
                desiredBw = int(c.getDesiredBw(time, pRun))
                if desiredBw <= bwShare:
                    # move to low bandwidth connctions
                    connBWB.remove(c)
                    connLBW.append(c)
                    # update low bandwidth sum
                    bwLowSum += desiredBw
                    c.setAvailableBw(desiredBw, time, pRun)
            round += 1
        
        #logger.debug("calculation done")
        #logger.debug("found {bwb} bandwidth bound connctions – bwShare={bwShare}".format(bwb=len(connBWB), bwShare=bwUnit(bwShare)))
        #logger.debug("found {low} low bandwidth connections – bwLowSum={bwLowSum}".format(low=len(connLBW), bwLowSum=bwUnit(bwLowSum)))

        # we are done - set available bandwidth for all bandwidth bound connctions
        for c in connBWB:
            c.setAvailableBw(bwShare, time, pRun)


    def getInfo(self):
        return "{0} @{1} {2}s".format(self.description, bwUnit(self.bandwidth), self.rtt)


    def __str__(self):
        storage = self._storageSwitch(self.pRun)
        conn = [c.getInfo() for c in storage.connections]
        return "{info} connections: {conn}".format(self.getInfo(), conn)


    def getSummary(self):
        return {'bandwidth'  : self.bandwidth,
                'rtt'        : self.rtt,  
                'description': self.description}
