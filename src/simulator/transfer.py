""" class to model transfers and keep their state """

from copy import copy
from enum import Enum
from simulator.eventSimulator import logAdapter, NOPREDICT

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logAdapter.setup("transfer")

transferCounterCounter = -1

def transferCounter():
    global transferCounterCounter
    transferCounterCounter += 1
    return transferCounterCounter

class state(Enum):
    NEW = 1
    ENABLED = 2
    ENQUEUED = 3
    ACTIVE = 4
    FINISHED = 5


class Transfer(object):

    def __init__(self, size, origin, ssl, harStartTime=None, harFinishTime=None, objectTimings=None):
        assert size > 0
        assert len(origin) > 0

        self.children = []
        self.ssl = ssl
        self.origin = origin
        self.size = size
        self.harStartTime = harStartTime
        self.harFinishTime = harFinishTime
        self.objectTimings = objectTimings
        self.rStorage = Transfer.TransferStorage(size)
        self.pStorage = None
        self.pRun = NOPREDICT
        self.id = transferCounter()
        #logger.debug("created transfer {info}".format(info=self.getInfo()))


    class TransferStorage(object):
        def __init__(self, size):
            self.outstandingBytes = size
            self.state = state.NEW
            self.startTime = None
            self.enableTime = None
            self.enqueueTime = None
            self.finishTime = None
            self.connection = None

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


    def addChild(self, child):
        self.children.append(child)


    def isNew(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.NEW


    def isEnabled(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.ENABLED


    def isEnqueued(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.ENQUEUED


    def isActive(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.ACTIVE


    def isFinished(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.FINISHED        


    def getOutstandingBytes(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.outstandingBytes

    def getTimes(self, pRun=NOPREDICT):
        storage = self._storageSwitch(pRun)
        return  {'startTime': storage.startTime,
                 'enableTime': storage.enableTime,
                 'enqueueTime': storage.enqueueTime,
                 'finishTime': storage.finishTime,
                 'harStartTime': self.harStartTime,
                 'harFinishTime': self.harFinishTime}
                

    def getConnection(self, pRun=NOPREDICT):
        return self._storageSwitch(pRun).connection 


    def transferBytes(self, amount, pRun):
        storage = self._storageSwitch(pRun)

        assert amount >= 0
        assert amount <= storage.outstandingBytes
        if storage.state != state.ACTIVE:
            #logger.debug("broken transfer: {t}".format(t=self))
            assert False

        storage.outstandingBytes -= amount

        #logger.debug("transfer {id} transferred {amount}bytes outstanding {to_go}bytes".format(id=self.id, amount=amount, to_go=storage.outstandingBytes))


    def enable(self, transferManager, time, pRun):
        storage = self._storageSwitch(pRun)
        assert storage.state == state.NEW

        storage.state = state.ENABLED
        storage.enableTime = time

        #logger.debug("enabled transfer {id}".format(id=self.id))


    def enqueue(self, connection, transferManager, time, pRun):
        storage = self._storageSwitch(pRun)
        assert storage.state == state.ENABLED
        #logger.debug("enqueueing transfer {id}".format(id=self.id))

        storage.state = state.ENQUEUED
        storage.connection = connection
        storage.enqueueTime = time

        transferManager.enqueueTransfer(self, time, pRun)


    def start(self, connection, transferManager, time, pRun):
        storage = self._storageSwitch(pRun)
        assert storage.state == state.ENABLED or storage.state == state.ENQUEUED
        #logger.debug("starting transfer {id}".format(id=self.id))

        storage.state = state.ACTIVE
        storage.connection = connection
        storage.startTime = time

        transferManager.startTransfer(self, time, pRun)
        

    def finish(self, connection, transferManager, time, pRun):
        storage = self._storageSwitch(pRun)
        assert storage.state == state.ACTIVE
        assert storage.outstandingBytes == 0
        assert storage.connection == connection
        
        storage.state = state.FINISHED
        storage.finishTime = time

        #logger.debug("finished transfer {id} --- transferred {size}bytes in {time:.3f}s".format(id=self.id, size=self.size, time=(storage.finishTime - storage.startTime)))

        transferManager.finishTransfer(self, time, pRun)



    def getInfo(self, pRun=None):
        return "id={id} {origin} {ssl} {size}Bytes".format(id=self.id, ssl="(s)" if self.ssl else "", origin=self.origin, size=self.size)


    def __str__(self):
        storage = self._storageSwitch(self.pRun)
        storageString = "{state} {out}Bytes outstanding, sT {st}s enT {ent}s eqT {eqt}s fT {ft}s".format(state=storage.state, out=storage.outstandingBytes, st=storage.startTime, ent=storage.enableTime, eqt=storage.enqueueTime, ft=storage.finishTime)
        return "{info} {children} {storage}".format(info=self.getInfo(self.pRun), storage=storageString, children=[c.getInfo() for c in self.children])


    def getSummary(self):
        return {'id': self.id,
                'origin': self.origin, 
                'ssl': self.ssl, 
                'size': self.size, 
                'children': [c.id for c in self.children] if self.children else [],
                'times': self.getTimes()}
