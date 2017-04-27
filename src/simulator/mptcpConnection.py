""" class to model MPTCP connections """

from enum import Enum
from copy import copy
from simulator.eventSimulator import Event, logAdapter, NOPREDICT
from simulator.connection import Connection, state, connectionCounter
from simulator.tcpConnection import TcpConnection, ssState, BW_TRANSFER_BYTES_ERROR_WARNING_THRESHOLD, EVENT_TRANSFER_BYTES_ERROR_WARNING_THRESHOLD
from simulator.interface import Interface
from simulator.globals import bwUnit

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logAdapter.setup("mptcpConnection")

class MptcpConnection(TcpConnection):

    def __init__(self, interfaces, idleTimeout, ssl, origin, transferManager, eventSimulator, pRun):
        assert interfaces
        for i in interfaces:
            assert type(i) == Interface

        self.interfaces = interfaces
        self.idleTimeout = idleTimeout
        self.eventSimulator = eventSimulator
        self.transferManager = transferManager
        self.ssl = ssl
        self.origin = origin
        self.id = connectionCounter()

        if pRun == NOPREDICT:
            self.rStorage = MptcpConnection.ConnectionStorage()
            self.pStorage = None
        else:
            self.rStorage = None
            self.pStorage = MptcpConnection.ConnectionStorage()
        self.pRun = pRun


    class ConnectionStorage(TcpConnection.ConnectionStorage):

        def __init__(self):
            self.transfers = []
            self.outstandingTransferBytesSum = 0
            self.transferredBytesSum = 0
            self.state = None
            self.mss = 1460
            self.availableBw = 0
            self.desiredBw = 0
            self.nextEvent = None
            self.idleTimestamp = None
            self.currTransferFinishTime = None
            self.lastBwUpdate = 0
            self.lastBwUpdateTransferredBytesSum = 0
            self.subflows = []
            self.bwUpdateInProgress = False
        def clone(self):
            clone = copy(self)
            clone.transfers = self.transfers[:]
            clone.subflows = self.subflows[:]
            return clone


    # here comes the main state machine split over
    #   - inner class TransferEvent for event triggerd transitons
    #   - connect and add transfers for external triggered transtions
    #   both will trigger event re-generation through updateDesiredBw as changed
    #   bandwidth needs are the only reason for changed deadlines.
    #   - setAvailableBw for bandwidth-triggered re-calculation of event deadlines
    class TransferEvent(Event):
        def __init__(self, connection, time, description):
            self.conn = connection
            super().__init__(time, description)


        def _handleEvent(self, eventSimulator, time, pRun):
            # get all needed parameters from outer class
            conn = self.conn
            storage = conn._storageSwitch(pRun)
            currTransfer = storage.transfers[0] if storage.transfers else None

            # check event consistency and remove current event from upcoming list
            assert storage.nextEvent == self
            storage.nextEvent = None

            # maintain state machine of outer class

            # new transfer on idle connection will be handeled by addTransfer

            #logger.debug("connection state: {0}".format(storage.state))

            # transfer finished
            if storage.state == state.BUSY and currTransfer.getOutstandingBytes(pRun) == 0:
                #logger.debug("handle finished transfer")
                storage.transfers.remove(currTransfer)

                # transition to idle if no outstanding transfers and  re-calculate desired bandwidth
                if not storage.transfers:
                    # update state
                    storage.state = state.IDLE
                    storage.idleTimestamp = time
                    # update desired bandwith - will implicitly make subflowas idle
                    conn.updateDesiredBw(time, pRun)
                    # tell transfer and transfer manager
                    conn._notifyIdle(storage, time, pRun)
                    currTransfer.finish(conn, conn.transferManager, time, pRun)

                # scheduling outstanding transfer - as bandwidth will most likely not change, force re-schduling
                elif storage.transfers:
                    # start new transfer
                    storage.transfers[0].start(conn, conn.transferManager, time, pRun)
                    conn.updateDesiredBw(time, pRun)
                    conn._scheduleNextEvent(time, pRun)
                    # tell transfer and transfer manager
                    currTransfer.finish(conn, conn.transferManager, time, pRun)

            # idle connection timed out
            elif storage.state == state.IDLE and storage.idleTimestamp + conn.idleTimeout >= time:
                #logger.debug("handle connection timed out - closing")
                conn.close(time, pRun)
                # no more events to be scheduled

            # broken state machine
            else:
                #logger.debug("broken TCP connection state machine:\n{s}".format(s=conn))
                assert False

    # connect will generate and connect the first subflow
    def connect(self, time, pRun):
        storage = self._storageSwitch(pRun)
        
        # set state
        storage.state = state.IDLE
        
        # start first subflow
        handshakeDelay = self.interfaces[0].rtt * (2 if not self.ssl else 4)
        subflow = MptcpSubflow(self, handshakeDelay, self.interfaces[0], self.eventSimulator, pRun)
        subflow.connect(time, pRun)
        storage.subflows.append(subflow)

        # register at the event simulator
        self.eventSimulator.registerTickListener(self, pRun)

        # notify others
        self._notifyNew(storage, time, pRun)


    def onSubflowHandshakeDone(self, subflow, time, pRun):
        storage = self._storageSwitch(pRun)
        assert type(subflow) == MptcpSubflow
        assert type(storage.subflows[0]) == MptcpSubflow

        # first subflow
        if subflow == storage.subflows[0]:
            #logger.debug("first subflow handshake done - starting other subflows")
            # start other subflows
            for i in self.interfaces[1:]:
                handshakeDelay = i.rtt * 2
                newSubflow = MptcpSubflow(self, handshakeDelay, i, self.eventSimulator, pRun)
                newSubflow.connect(time, pRun)
                storage.subflows.append(newSubflow)
        #else:
        #    logger.debug("other subflow handshake done - start using it")


    def close(self, time, pRun):
        storage = self._storageSwitch(pRun)
        assert storage.state != state.CLOSED

        for sf in storage.subflows:
            #logger.debug("closing subflow {sf}".format(sf=sf.getInfo(pRun)))
            sf.close(time, pRun)

        if storage.nextEvent: 
            storage.nextEvent.disableEvent(pRun)
        self.eventSimulator.unregisterTickListener(self, pRun)

        storage.state = state.CLOSED
        self._notifyClosed(storage, time, pRun)


    def addTransfer(self, transfer, time, pRun):
        assert transfer.ssl == self.isSSL()
        assert transfer.isEnabled(pRun)
        storage = self._storageSwitch(pRun)

        # add transfer and update desired bandwidth
        storage.transfers.append(transfer)
        storage.outstandingTransferBytesSum += transfer.getOutstandingBytes(pRun)

        # start transfer on idle connection and re-schedule events
        if storage.state == state.IDLE:
            assert storage.transfers[0] == transfer
            transfer.start(self, self.transferManager, time, pRun)
            storage.state = state.BUSY
            # re-calculate desired bandwidth - will schedule next event implicitly
            self.updateDesiredBw(time, pRun)
            self._notifyBusy(storage, time, pRun)
        # enqueue on busy connection
        elif storage.state == state.BUSY:
            assert storage.transfers[0] != transfer
            transfer.enqueue(self, self.transferManager, time, pRun)
            # re-calculate desired bandwidth - will schedule next event implicitly
            self.updateDesiredBw(time, pRun)
        # something went wrong
        else:
            logger.error("added transfer on unsuiteable connection {c}".format(c=self))
            assert False


    def updateDesiredBw(self, time, pRun):
        storage = self._storageSwitch(pRun)
        newDesiredBw = None

        # busy connection - transfer data
        if storage.state == state.BUSY:
            # we do no slowstart - so only one desired estimate
            # make sure that we don't drop below availableBw in case outstandingTransferBytesSum gets tiny
            newDesiredBw = max(int(storage.outstandingTransferBytesSum / self.interfaces[0].getRTT()), 1)

        # if we are idle, we need no bandwidth
        elif storage.state == state.IDLE:
            newDesiredBw = 0

        # something strange happend
        else:
            assert False

        # tell subflows if neccessary
        if newDesiredBw != storage.desiredBw:
            storage.desiredBw = newDesiredBw
            storage.bwUpdateInProgress = True
            for sf in storage.subflows:
                sf.updateDesiredBw(time, pRun)
            storage.bwUpdateInProgress = False
            self.updateAvailableBw(time, pRun)


    def setAvailableBw(self, availableBw, time, pRun):
        storage = self._storageSwitch(pRun)

        # only do something if bandwidth changed
        if storage.availableBw != availableBw:
            #logger.debug("updating available bandwidth on MPTCP subflow id={id} – old={old} new={new}".format(id=self.id, old=bwUnit(storage.availableBw), new=bwUnit(availableBw)))

            # make sure we got no bandwidth share if we did not ask for one
            if storage.state == state.IDLE:
                assert availableBw == 0

            # update local cache
            storage.availableBw = availableBw

            # update error cache
            storage.lastBwUpdate = time
            storage.lastBwUpdateTransferredBytesSum = storage.transferredBytesSum

            # re-calculate next event
            self._scheduleNextEvent(time, pRun)


    def updateAvailableBw(self, time, pRun):
        storage = self._storageSwitch(pRun)

        if storage.bwUpdateInProgress == True:
            pass
        else:
            newBandwidthSum = 0
            for sf in storage.subflows:
                newBandwidthSum += sf.getAvailableBw(time, pRun)

            self.setAvailableBw(newBandwidthSum, time, pRun)


    # re-schedule event if needed
    def _checkReplaceEvent(self, storage, nextTime, description, pRun):
        assert not storage.nextEvent or type(storage.nextEvent) == MptcpConnection.TransferEvent

        if storage.nextEvent and storage.nextEvent.time == nextTime and storage.nextEvent.description == description:
            return
        elif storage.nextEvent:
            storage.nextEvent.disableEvent(pRun)
            storage.nextEvent = None

        # need a new event
        storage.nextEvent = MptcpConnection.TransferEvent(self, nextTime, description)
        self.eventSimulator.addEvent(storage.nextEvent, pRun)


    def _scheduleNextEvent(self, time, pRun):
        storage = self._storageSwitch(pRun)
        nextTime = None
        description = ""

        # we are idle - calculate timeout
        if storage.state == state.IDLE:
            self._checkReplaceEvent(storage, storage.idleTimestamp + self.idleTimeout, "tear down idle connection: {conn}".format(conn=self.getInfo(pRun)), pRun)
        # in mptcp master       
        elif storage.state == state.BUSY and storage.availableBw == 0:
            pass
        elif storage.state == state.BUSY and storage.availableBw > 0:
            transferFinishTime = storage.transfers[0].getOutstandingBytes(pRun) / storage.availableBw
            assert storage.transfers[0].getOutstandingBytes(pRun) == round(storage.availableBw*transferFinishTime)
            self._checkReplaceEvent(storage, time+transferFinishTime, "transfer finishing in mptcp master", pRun)
            storage.currTransferFinishTime = time+transferFinishTime
        else:
            assert False


    def _tickTime(self, start, end, pRun):
        # stuff info from class
        storage = self._storageSwitch(pRun)

        # busy connection - transfer data
        if storage.state == state.BUSY:
            currTransfer = storage.transfers[0]
            #logger.debug(self)
            assert currTransfer.isActive(pRun)

            # calculate how much we will transfer (naïve)
            delta = end - start
            transferBytes = int(storage.availableBw*delta) 

            # don't overshoot due to numeric stability issues
            # first, calculate how many bytes should have been transferred since last bandwidth update
            bwRoundTransferredBytes = int(storage.availableBw * (end - storage.lastBwUpdate))
            # second, calculate how many bytes in total should have been transferred after this round
            # by bandwith update round:
            bwRoundTransferredBytesSum = int(storage.lastBwUpdateTransferredBytesSum+bwRoundTransferredBytes)  
            # by tick times round:
            ttTransferredBytesSum = int(storage.transferredBytesSum+transferBytes)
            # finally, fix transferBytes if neccessary
            if ttTransferredBytesSum > bwRoundTransferredBytesSum:
                # alculate the differnece - how much did we overshoot in this bandwith update round
                bwRoundTransferredBytesError = ttTransferredBytesSum - bwRoundTransferredBytesSum
                if abs(bwRoundTransferredBytesError) > BW_TRANSFER_BYTES_ERROR_WARNING_THRESHOLD:
                    logger.warning("overshot {b}bytes due to numeric stability issues - adjusting".format(b=bwRoundTransferredBytesError))
                transferBytes -= bwRoundTransferredBytesError

                # fix rounding error that leads to negative transferByte amounts
                if transferBytes < 0:
                    transferBytes = 0

            # handle rounding problems that prevet events from finsihing
            transferBytesError =  transferBytes - currTransfer.getOutstandingBytes(pRun)
            if end == storage.currTransferFinishTime and transferBytesError < 0 or transferBytesError > 0:
                if abs(transferBytesError) > EVENT_TRANSFER_BYTES_ERROR_WARNING_THRESHOLD:
                    logger.warning("{ou}shot transfer {t} by {b}bytes - using exact bytes from event calculation".format(t=currTransfer.getInfo(pRun), b=abs(transferBytesError), ou= "over" if transferBytesError > 0 else "under") )
                transferBytes = currTransfer.getOutstandingBytes(pRun)

            # slow start state is handled in subflows

            currTransfer.transferBytes(transferBytes, pRun)
            storage.transferredBytesSum += transferBytes
            storage.outstandingTransferBytesSum -= transferBytes


        # if we are idle, time if of no interest for us
        elif storage.state == state.IDLE:
            pass

        # something strange happend
        else:
            assert False



    def getInfo(self, pRun=None):
        storage = self._storageSwitch(pRun if pRun else self.pRun)
        return "MPTCP id={id} {origin} {ssl} ({state}/*) togo {trans}T {out}Bytes".format(origin=self.origin,
                                                                                          id=self.id,
                                                                                          ssl="(s)" if self.isSSL() else "",
                                                                                          trans=len(storage.transfers),
                                                                                          out=storage.outstandingTransferBytesSum,
                                                                                          state=storage.state)
    

    def getSummary(self, pRun=NOPREDICT):
        storage = self._storageSwitch(pRun)
        return {'id': self.id,
                'transferredBytes': storage.transferredBytesSum,
                'transfers': [t.id for t in storage.transfers],
                'type': 'MPTCP',
                'subflows': [sf.getSummary() for sf in storage.subflows]}

 
class MptcpSubflow(TcpConnection):

    def __init__(self, master, handshakeDelay, interface, eventSimulator, pRun):
        assert type(interface) == Interface

        self.master = master
        self.interface = interface
        self.eventSimulator = eventSimulator
        self.handshakeDelay = handshakeDelay
        if pRun == NOPREDICT:
            self.rStorage = TcpConnection.ConnectionStorage()
            self.pStorage = None
        else:
            self.rStorage = None
            self.pStorage = TcpConnection.ConnectionStorage()
        self.pRun = pRun
        self.id = connectionCounter()


    def _notifyNew(self, storage, time, pRun):
        assert storage.state == state.IDLE
        # we are a subflow - do not notify transferManager


    def _notifyIdle(self, storage, time, pRun):
        assert storage.state == state.IDLE
        # we are a subflow - do not notify transferManager


    def _notifyBusy(self, storage, time, pRun):
        assert storage.state == state.BUSY
        # we are a subflow - do not notify transferManager


    def _notifyClosed(self, storage, time, pRun):
        assert storage.state == state.CLOSED
        # we are a subflow - do not notify transferManager


    def isSSL(self):
        return self.master.isSSL()


    def addTransfer(self, transfer, time, pRun):
        assert False


    # here comes the main state machine split over
    #   - inner class TransferEvent for slowstart events
    #   - connect for external triggered transtions
    #   both will trigger event re-generation through updateDesiredBw as changed
    #   bandwidth needs are the only reason for changed deadlines.
    #   - setAvailableBw for bandwidth-triggered re-calculation of event deadlines
    class TransferEvent(Event):
        def __init__(self, connection, time, description):
            self.conn = connection
            super().__init__(time, description)


        def _handleEvent(self, eventSimulator, time, pRun):
            # get all needed parameters from outer class
            conn = self.conn
            master = conn.master
            storage = conn._storageSwitch(pRun)

            # check event consistency and remove current event from upcoming list
            assert storage.nextEvent == self
            storage.nextEvent = None

            # maintain state machine of outer class

            # still in slowstart and not finished
            if master.isBusy(pRun) and storage.ssState == ssState.SS:
                # re-calculate desired bandwidth - will schedule next event implicitly
                conn.updateDesiredBw(time, pRun)

            # new and entering slowstart
            elif storage.ssState == ssState.NEW:
                # re-calculate desired bandwidth - will schedule next event implicitly
                storage.ssState = ssState.SS
                master.onSubflowHandshakeDone(conn, time, pRun)
                conn.updateDesiredBw(time, pRun)

            # broken state machine
            else:
                assert False


    def updateDesiredBw(self, time, pRun):
        storage = self._storageSwitch(pRun)
        master = self.master
        newDesiredBw = None

        # busy connection - transfer data
        if master.isBusy(pRun):
            storage.state = state.BUSY
            # based on slow start state, we have to do different things
            # new connection - no need for bandwidth yet
            if storage.ssState == ssState.NEW:
                newDesiredBw = 0
            # slowstart - get from congestion window
            elif storage.ssState == ssState.SS:
                newDesiredBw = int(storage.cwnd / self.interface.getRTT())
            elif storage.ssState == ssState.CA:
                newDesiredBw = master.getDesiredBw(time, pRun)

        # if we are idle, we need no bandwidth
        elif master.isIdle(pRun):
            storage.state = state.IDLE
            newDesiredBw = 0

        # something strange happend
        else:
            assert False

        # tell interface if neccessary
        if newDesiredBw != storage.desiredBw:
            storage.desiredBw = newDesiredBw
            self.interface.updateConnectionBwShare(time, pRun)


    def setAvailableBw(self, availableBw, time, pRun):
        storage = self._storageSwitch(pRun)
        master = self.master

        # only do something if bandwidth changed or if in slowstart
        if storage.availableBw != availableBw or storage.ssState == ssState.SS:

            # update local cache
            storage.availableBw = availableBw

            # make sure we got no bandwidth share if we did not ask for one
            if master.isIdle(pRun) or storage.ssState == ssState.NEW:
                assert availableBw == 0

            # if we are busy, we have to do different things based on slow start state
            elif master.isBusy(pRun):
                rtt = self.interface.getRTT()

                # check if we dropped out of slowstart
                if storage.ssState == ssState.SS:
                    if int(storage.cwnd / rtt) > availableBw:
                        storage.ssState = ssState.CA
                        storage.cwnd = availableBw * rtt
                        # update desired bandwitdh to master's desired Bw or slowstart round
                        # either might fail in case of stupid co-incidence
                        storage.desiredBw = max(master.getDesiredBw(time, pRun), storage.desiredBw)
                    else:
                        # we did not drop out of slow start - we got what we wanted
                        # as we entedrd next round, our desired bandwitdh increased
                        pass

                # set congestion window if not in slowstart
                elif storage.ssState == ssState.CA:
                    storage.cwnd = availableBw * rtt

            # inform master about recent changes
            master.updateAvailableBw(time, pRun)

            # re-calculate next event
            self._scheduleNextEvent(time, pRun)


    # re-schedule event if needed
    def _checkReplaceEvent(self, storage, nextTime, description, pRun):
        if storage.nextEvent and storage.nextEvent.time == nextTime and storage.nextEvent.description == description:
            return
        elif storage.nextEvent:
            storage.nextEvent.disableEvent(pRun)
            storage.nextEvent = None

        # need a new event
        storage.nextEvent = MptcpSubflow.TransferEvent(self, nextTime, description)
        self.eventSimulator.addEvent(storage.nextEvent, pRun)


    def _scheduleNextEvent(self, time, pRun):
        storage = self._storageSwitch(pRun)
        master = self.master

        if master.isBusy(pRun) and storage.ssState == ssState.SS:
            rtt = self.interface.getRTT()
            self._checkReplaceEvent(storage, time+rtt, "slowstart round finishing", pRun)
        elif storage.nextEvent:
            storage.nextEvent.disableEvent(pRun)
            storage.nextEvent = None


    def _tickTime(self, start, end, pRun):
        # stuff info from class
        storage = self._storageSwitch(pRun)

        # busy connection - transfer data
        if storage.state == state.BUSY:

            # calculate how much we will transfer (naïve)
            delta = end - start
            transferBytes = int(storage.availableBw*delta) 

            # all magic and transfer progress is done in master

            # based on slow start state, we have to do different things
            if storage.ssState == ssState.NEW:
                pass

            elif storage.ssState == ssState.SS:
                storage.transferredBytesSum += transferBytes
                storage.outstandingTransferBytesSum -= transferBytes
                storage.cwnd += transferBytes
    
            elif storage.ssState == ssState.CA:
                storage.transferredBytesSum += transferBytes
                storage.outstandingTransferBytesSum -= transferBytes

        # if we are idle, time if of no interest for us
        elif storage.state == state.IDLE:
            pass

        # something strange happend
        else:
            assert False



    def getInfo(self, pRun=None):
        storage = self._storageSwitch(pRun if pRun else self.pRun)
        return "MPTCP subflow id={id} ({state}/{ssState}) on {iface} for {master}".format(iface=self.interface.getInfo(),
                                                                                          id=self.id,
                                                                                          master=self.master.getInfo(),
                                                                                          state=storage.state,
                                                                                          ssState=storage.ssState)


    def getSummary(self, pRun=NOPREDICT):
        storage = self._storageSwitch(pRun)
        return {'id': self.id,
                'transferredBytes': storage.transferredBytesSum,
                'interface': self.interface.description}
