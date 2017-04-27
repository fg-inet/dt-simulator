""" policy junkpile - this is somewhat of the main program... """

from itertools import combinations, permutations
from simulator.eventSimulator import NOPREDICT, logAdapter
from simulator.globals import progressFH
from random import sample

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logAdapter.setup("policy")

DEFAULT_IDLE_TIMEOUT = 30.0
DEFAULT_GLOBAL_LIMIT = 17
DEFAULT_HOST_LIMIT = 6

class Policy(object):

    def __init__(self):
        self.transferManager = None


    def prepare (self, transferManager):
        self.transferManager = transferManager
        return self


    def _predictNewConnection(self, transfer, interfaces, transferManager):

        print('.', end="", file=progressFH)

        # predict the completion time of the given transfer using no existing connection
        transferTimes = transferManager.predictTransfer(transfer, None, interfaces, DEFAULT_IDLE_TIMEOUT)
        return {'time': transferTimes['finishTime'], 'conn': None, 'ifaces': interfaces}


    def _predictPipelinedConnection(self, transfer, connection, transferManager):
        assert len(transferManager.interfaces) >= 1

        print('.', end="", file=progressFH)

        # predict the transfer completion time when using an existing connection
        transferTimes =  transferManager.predictTransfer(transfer, connection, None, DEFAULT_IDLE_TIMEOUT)
        return {'time': transferTimes['finishTime'], 'conn': connection, 'ifaces': None}


    def _predictPipelinedConnections(self, transfer, connections, transferManager):
        predictionBestPipe = {'time': float('Inf'), 'conn': None, 'ifaces': None}

        for connection in connections:
            # skip all connections that are on a different host or differ in ssl
            if connection.origin != transfer.origin or connection.ssl != transfer.ssl:
                continue

            predictionNew = self._predictPipelinedConnection(transfer, connection, transferManager)

            if predictionNew['time'] < predictionBestPipe['time']:
                predictionBestPipe = {'time': predictionNew['time'], 'conn': connection, 'ifaces': None}

        return predictionBestPipe


    def predict(self, transfer, transferManager):
        pass


    def _executePrediction(self, prediction, transfer, transferManager, time):
        # make sure prediction is valid
        # either connection or interfaces must be set (not both)
        assert not(prediction['conn'] != None and prediction['ifaces'] != None)
        assert not(prediction['conn'] == None and prediction['ifaces'] == None)
        assert prediction['time'] > 0

        if prediction['conn']:
            assert prediction['conn'].origin == transfer.origin
            assert prediction['conn'].ssl == transfer.ssl
            assert not prediction['conn'].isClosed(NOPREDICT)

        if len(transferManager.getBusyConnections()) + len(transferManager.getIdleConnections()) >= DEFAULT_GLOBAL_LIMIT:
            closingCandidate = transferManager.getClosingCandidate()

            # check if we have a closing candidate
            if closingCandidate and closingCandidate != prediction['conn']:
                #logger.debug("closing idle connection {conn}".format(conn=closingCandidate))
                closingCandidate.close(time, NOPREDICT)

        transferManager.scheduleTransfer(transfer, prediction['conn'], prediction['ifaces'], DEFAULT_IDLE_TIMEOUT)


    # is called when a transfer finishes - check deferred transfers if we can schedule them now
    def notify(self, transferManager, time):
        print(' ', end="", file=progressFH)

        enabledTransfers = transferManager.getEnabledTransfers()
        if enabledTransfers:
            #logger.debug("checking {transLen} enabled transfers: {trans}".format(transLen=len(enabledTransfers), trans=[t.getInfo() for t in enabledTransfers]))

            if len(transferManager.getBusyConnections()) >= DEFAULT_GLOBAL_LIMIT:
                #logger.debug("can not schedule enabled transfer - over global limit: {limit}".format(limit=len(transferManager.getBusyConnections())))
                print('x', end="", file=progressFH)
                return
            else:
                for transfer in enabledTransfers:
                    # if we reached the per-host limit
                    hostLimit = len(transferManager.getBusyConnectionsForOrigin(transfer.origin))
                    if hostLimit >= DEFAULT_HOST_LIMIT:
                        #logger.debug("can not schedule enabled - over host limit: {limit}".format(limit=hostLimit))
                        print('-', end="", file=progressFH)
                        continue
                    else:
                        #logger.debug("scheduling enabled transfer: {trans}".format(trans=transfer.getInfo()))
                        print('<', end="", file=progressFH)
                        prediction = self.predict(transfer, transferManager)
                        self._executePrediction(prediction, transfer, transferManager, time)
                        print('>', end="", file=progressFH, flush=True)


    def getInfo(self):
        return "{name}".format(name=self.__class__.__name__)


    def getSummary(self):
        return {'name': self.getInfo()}      


class useOneInterfaceOnly(Policy):

    def __init__(self, interface):
        super().__init__()
        self.interface = interface

    def predict(self, transfer, transferManager):
        predictionNew = self._predictNewConnection(transfer, [self.interface], transferManager)
        predictionPipe = self._predictPipelinedConnections(transfer, self.interface.getConnections(), transferManager)

        return predictionNew if predictionNew['time'] < predictionPipe['time'] else predictionPipe

    def getInfo(self):
        return "{name}({interface})".format(name=self.__class__.__name__, interface=self.interface.description)


class roundRobin(Policy):

    def __init__(self, interfaces):
        super().__init__()
        self.interfaces = interfaces
        self.nextInterfaceId = 0


    def predict(self, transfer, transferManager):
        interface = self.interfaces[self.nextInterfaceId]
        prediction = useOneInterfaceOnly(interface).predict(transfer, transferManager)
        self.nextInterfaceId = (self.nextInterfaceId+1) % len(self.interfaces)

        return prediction

    def getInfo(self):
        return "{name}({interface})".format(name=self.__class__.__name__, interface="+".join([x.description for x in self.interfaces]))


class earliestArrivalFirst(Policy):

    def predict(self, transfer, transferManager):
        predictionBest = {'time': float('Inf'), 'conn': None, 'ifaces': None}

        for interface in transferManager.interfaces:
            predictionNew = useOneInterfaceOnly(interface).predict(transfer, transferManager)
            if predictionNew['time'] < predictionBest['time']:
                predictionBest = predictionNew

        return predictionBest


class mptcpFullMeshIFListPolicy(Policy):
    
    def __init__(self, interfaces):
        super().__init__()
        self.interfaces = interfaces
        
    def predict(self, transfer, transferManager):

        predictionNew = self._predictNewConnection(transfer, self.interfaces , transferManager)
        predictionPipe = self._predictPipelinedConnections(transfer, transferManager.getConnectionCandidates(), transferManager)

        return predictionNew if predictionNew['time'] < predictionPipe['time'] else predictionPipe

    def getInfo(self):
        return "{name}({interface})".format(name=self.__class__.__name__, interface="+".join([x.description for x in self.interfaces]))

class mptcpFullMeshPolicy(Policy):
    def predict(self, transfer, transferManager):

        predictionNew = self._predictNewConnection(transfer, sample(transferManager.interfaces, len(transferManager.interfaces)), transferManager)
        predictionPipe = self._predictPipelinedConnections(transfer, transferManager.getConnectionCandidates(), transferManager)

        return predictionNew if predictionNew['time'] < predictionPipe['time'] else predictionPipe


class earliestArrivalFirstMPTCP(Policy):
    def predict(self, transfer, transferManager):
        # predict new transfer on all existing connections - both single interface and mptcp connections
        predictionBest = self._predictPipelinedConnections(transfer, transferManager.getConnectionCandidates(), transferManager)

        # new connections - single interface
        for interface in transferManager.interfaces:
            predictionNew = self._predictNewConnection(transfer, [interface], transferManager)
            if predictionNew['time'] < predictionBest['time']:
                predictionBest = predictionNew

        # mptcp combinations
        for i in range(2, len(transferManager.interfaces)+1):
            for interfacecombination in combinations(transferManager.interfaces, i):
                for interfaces in permutations(interfacecombination):
                    predictionNew = self._predictNewConnection(transfer, interfaces, transferManager)
                    if predictionNew['time'] < predictionBest['time']:
                        predictionBest = predictionNew

        return predictionBest
