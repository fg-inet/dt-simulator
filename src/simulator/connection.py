""" abstract class for all kinds of simulated connection """

from copy import copy
from enum import Enum
from simulator.eventSimulator import TickListener, NOPREDICT

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


class state(Enum):
    IDLE = 1
    BUSY = 2
    CLOSED = 3

connectionCounterCounter = -1

def connectionCounter():
    global connectionCounterCounter
    connectionCounterCounter += 1
    return connectionCounterCounter

class Connection(TickListener):

    def __init__(self, idleTimeout, ssl, origin, transferManager, eventSimulator):
        self.rStorage = Connection.ConnectionStorage()
        self.pStorage = None
        self.pRun = NOPREDICT
        self.idleTimeout = idleTimeout
        self.eventSimulator = eventSimulator
        self.transferManager = transferManager
        self.ssl = ssl
        self.origin = origin
        self.id = connectionCounter()


    class ConnectionStorage(object):
        def __init__(self):
            self.desiredBw = 0.0
            self.availableBw = 0.0
            self.idleTimestamp = None

        def clone(self):
            clone = copy(self)
            return clone


    def _storageSwitch(self, pRun):
        if self.pRun != pRun:
            self.pStorage = self.rStorage.clone()
            self.pRun = pRun

        if pRun == NOPREDICT:
            return self.rStorage
        else:
            return self.pStorage


    def _notifyNew(self, storage, time, pRun):
        assert storage.state == state.IDLE


    def _notifyIdle(self, storage, time, pRun):
        assert storage.state == state.IDLE
        self.transferManager.idledConnection(self, time, pRun)


    def _notifyBusy(self, storage, time, pRun):
        assert storage.state == state.BUSY
        self.transferManager.busiedConnection(self, time, pRun)


    def _notifyClosed(self, storage, time, pRun):
        assert storage.state == state.CLOSED
        self.transferManager.closedConnection(self, time, pRun)


    def getIdleTimestamp(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.idleTimestamp


    def getDesiredBw(self, time, pRun):
        storage = self._storageSwitch(pRun)
        return storage.desiredBw


    def getAvailableBw(self, time, pRun):
        storage = self._storageSwitch(pRun)
        return storage.availableBw


    def setAvailableBw(self, availableBw, time, pRun):
        storage = self._storageSwitch(pRun)
        
        # only do something if bandwidth changed
        if storage.availableBw != availableBw:

            # update local cache
            storage.availableBw = availableBw
            

    def _tickTime(self, start, end, pRun):
        pass

        
    def __str__(self):
        return ""
