""" state keeping of transfers and """

import logging
import json
from copy import deepcopy
from simulator.eventSimulator import EventSimulator, logAdapter, NOPREDICT
from simulator.tcpConnection import TcpConnection
from simulator.mptcpConnection import MptcpConnection
from simulator.connection import Connection

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logAdapter.setup("transferManager")

class TransferManager(object):

    def __init__(self):
        self.policy = None
        self.eventSimulator = None

        self.finishTime = None

        self.transfers = []
        self.newTransfers = []
        self.enabledTransfers = []
        self.enqueuedTransfers = []
        self.activeTransfers = []
        self.finishedTransfers = []

        self.interfaces = []

        self.connections = []

        self.busyConnections = set()
        self.idleConnections = set()
        self.closedConnections = set()
        self.connectionOrigin = {}

        self.pRun = NOPREDICT
        self.pTransfer = None



    def idledConnection(self, connection, time, pRun):
        assert pRun == self.pRun
        if pRun == NOPREDICT:
            # update busyConnections and connectionOrigin
            self.busyConnections.remove(connection)  
            self.connectionOrigin[connection.origin].remove(connection)
            self.idleConnections.add(connection)
            # notify policy that there might be transfers to schedule
            if self.policy:
                self.policy.notify(self, time)


    def busiedConnection(self, connection, time, pRun):
        assert pRun == self.pRun
        if pRun == NOPREDICT:
            # connection might be unknown at all - so check first
            if connection in self.idleConnections:
                self.idleConnections.remove(connection)  
            self.busyConnections.add(connection)
            # maintain connectionOrigin
            if not self.connectionOrigin.get(connection.origin):
                self.connectionOrigin[connection.origin] = set()
            self.connectionOrigin[connection.origin].add(connection)


    def closedConnection(self, connection, time, pRun):
        assert pRun == self.pRun
        if pRun == NOPREDICT:
            if  connection in self.idleConnections:
                self.idleConnections.remove(connection)
            elif connection in self.busyConnections:
                logger.warning("got notification that active connection {c} was closed".format(c=connection.getInfo()))
                self.busyConnections.remove(connection)
            else:
                assert False
            self.closedConnections.add(connection)


    def getConnectionCandidates(self):
        return self.busyConnections.union(self.idleConnections)


    def getBusyConnectionsForOrigin(self, origin):
        return self.connectionOrigin.get(origin, set())


    def getIdleConnections(self):
        return self.idleConnections 


    def getBusyConnections(self):
        return self.busyConnections 


    def getClosingCandidate(self, pRun=NOPREDICT):
        if self.idleConnections:
            return min(self.idleConnections, key=lambda c: c.getIdleTimestamp(pRun) )
        else:
            return set()


    def addTransfer(self, transfer):
        assert transfer.isNew(NOPREDICT)

        self.transfers.append(transfer)
        self.newTransfers.append(transfer)


    def addTransfers(self, transfers):
        for t in transfers:
            self.addTransfer(t)


    def getEnabledTransfers(self):
        return list(self.enabledTransfers)


    def enableTransfer(self, transfer, time=0, pRun=NOPREDICT):
        assert pRun == self.pRun
        assert not transfer.isEnabled(pRun)

        # we will be informed of transfers that get enabled during pRuns - ignore for now
        if pRun != NOPREDICT:
            return

        # inform transfer and add to enabled list,
        self.newTransfers.remove(transfer)
        transfer.enable(self, time, pRun)
        self.enabledTransfers.append(transfer)

        # notify policy that there might be transfers to schedule
        if self.eventSimulator and self.policy:
            self.policy.notify(self, time)


    def enqueueTransfer(self, transfer, time, pRun):
        assert pRun == self.pRun

        # real run - just move between lists
        if pRun == NOPREDICT:
            self.enabledTransfers.remove(transfer)
            self.enqueuedTransfers.append(transfer)


    def startTransfer(self, transfer, time, pRun):
        assert pRun == self.pRun

        # real run - just move between lists
        if pRun == NOPREDICT:
            self.activeTransfers.append(transfer)
            if transfer in self.enqueuedTransfers:
                self.enqueuedTransfers.remove(transfer)
            else:
                self.enabledTransfers.remove(transfer)


    def finishTransfer(self, transfer, time, pRun):
        assert pRun == self.pRun

        # real run - just move between lists
        if pRun == NOPREDICT:
            self.activeTransfers.remove(transfer)
            self.finishedTransfers.append(transfer)
            
            if transfer.children:
                for child in transfer.children:
                    self.enableTransfer(child, time, pRun)

            if len(self.finishedTransfers) == len(self.transfers):
                #logger.debug("finished all transfers in {time}s".format(time=time))
                self.finishTime = time


        # finsh pRun if transfer we are looking at finfishes
        elif transfer == self.pTransfer:
            self.eventSimulator.endPrecition(pRun)


    def _scheduleTransfer(self, transfer, connection, interfaces, idleTimeout, pRun):
        time = self.eventSimulator.getTime(pRun)
        # logger.debug("called with connection {conn} and interface {ifs} for transfers {trans} ".format(trans=transfer, ifs=interfaces, conn=connection))

        # schedule new connection on specified interface(s)
        if not connection and interfaces:
            if len(interfaces) == 1:
                connection = TcpConnection(interfaces[0], idleTimeout, transfer.ssl, transfer.origin, self, self.eventSimulator, pRun)
            else:
                connection = MptcpConnection(interfaces, idleTimeout, transfer.ssl, transfer.origin, self, self.eventSimulator, pRun)

            if pRun == NOPREDICT:
                # save connection to connection list 
                self.connections.append(connection)

            # tell connection to connect
            connection.connect(time, pRun)

        # schedule transfer on existing connection (i.e. pipelining)
        elif connection and not interfaces:
            assert not connection.isClosed(pRun)
        # parameter error
        else:
            assert False

        connection.addTransfer(transfer, time, pRun)



    def scheduleTransfer(self, transfer, connection, interfaces, idleTimeout):
        self._scheduleTransfer(transfer, connection, interfaces, idleTimeout, NOPREDICT)


    def predictTransfer(self, transfer, connection, interfaces, idleTimeout):

        pRun = self.eventSimulator.beginPrediction()
        self.pRun = pRun
        self.pTransfer = transfer
        #logger.debug("stating prediction of {0} on {1}".format(transfer.getInfo(), [i.getInfo() for i in interfaces] if interfaces else connection.getInfo() ))
        self._scheduleTransfer(transfer, connection, interfaces, idleTimeout, pRun)
        self.eventSimulator.predictionRun(pRun)

        self.pRun = NOPREDICT
        #logger.debug("finished prediction of {0} on {1}".format(transfer.getInfo(), [i.getInfo() for i in interfaces] if interfaces else connection.getInfo()))

        return transfer.getTimes(pRun)


    def runTransfers(self, interfaces, policy):

        # copy template transfer manager and prepare simulation
        tm = deepcopy(self)
        tm.eventSimulator = EventSimulator()
        tm.interfaces = deepcopy(interfaces)
        tm.policy = policy.prepare(tm)
        assert tm.policy

        #logger.debug("starting simulation")

        # notify policy that there might be transfers to schedule
        tm.policy.notify(tm, 0)

        # run simulation
        tm.eventSimulator.realRun()

        #logger.debug("finished simulation")

        # check whether all transfers are finished
        for transfer in tm.transfers:
            if not transfer.isFinished(NOPREDICT):
                logger.error("transfer: {trans} not finished".format(trans=transfer.getInfo()))
            assert transfer.isFinished(NOPREDICT)

        return tm, tm.finishTime


    def dumpJson(self, fh):
        json.dump({
            'policy':       self.policy.getSummary(),
            'interfaces':   [i.getSummary() for i in self.interfaces],
            'connections':  [i.getSummary() for i in self.connections],
            'transfers' :   [t.getSummary() for t in self.transfers]
            }, fh, indent="\t")
