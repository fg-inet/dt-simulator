""" class to model regular TCP connections """

from copy import copy
from enum import Enum
from simulator.globals import toMB, bwUnit
from simulator.eventSimulator import Event, logAdapter, NOPREDICT
from simulator.connection import Connection, state, connectionCounter 

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logAdapter.setup("connection")

BW_TRANSFER_BYTES_ERROR_WARNING_THRESHOLD = 8
EVENT_TRANSFER_BYTES_ERROR_WARNING_THRESHOLD = 16

class ssState(Enum):
    NEW = 1
    SS = 2
    CA = 3


class TcpConnection(Connection):

    def __init__(self, interface, idleTimeout, ssl, origin, transferManager, eventSimulator, pRun):

        self.interface = interface
        self.idleTimeout = idleTimeout
        self.eventSimulator = eventSimulator
        self.transferManager = transferManager
        self.ssl = ssl
        self.origin = origin
        self.handshakeDelay = self.interface.rtt * (2 if not self.ssl else 4)
        self.id = connectionCounter()

        if pRun == NOPREDICT:
            self.rStorage = TcpConnection.ConnectionStorage()
            self.pStorage = None
        else:
            self.rStorage = None
            self.pStorage = TcpConnection.ConnectionStorage()
        self.pRun = pRun


    class ConnectionStorage(object):

        def __init__(self):
            self.transfers = []
            self.outstandingTransferBytesSum = 0
            self.transferredBytesSum = 0
            self.state = None
            self.ssState = ssState.NEW
            self.mss = 1460
            self.availableBw = 0
            self.desiredBw = 0
            self.nextEvent = None   # invariant: only one active outstanding event per pRun/NOPREDICT 
            self.idleTimestamp = None
            self.cwnd = 10 * self.mss # was 3* according to Linux 2.6.32 updated to 10 following linux kernels >= 3.0.0
            self.currTransferFinishTime = None
            self.lastBwUpdate = 0
            self.lastBwUpdateTransferredBytesSum = 0


        def clone(self):
            clone = copy(self)
            clone.transfers = self.transfers[:]
            return clone


    def _storageSwitch(self, pRun):
        if self.pRun != pRun:
            self.pStorage = self.rStorage.clone()
            self.pRun = pRun

        if pRun == NOPREDICT:
            return self.rStorage
        else:
            return self.pStorage


    def isIdle(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.IDLE


    def isBusy(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.BUSY


    def isClosed(self, pRun):
        storage = self._storageSwitch(pRun)
        return storage.state == state.CLOSED


    def isSSL(self):
        return self.ssl


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

            # still in slowstart and not finished
            elif storage.state == state.BUSY and storage.ssState == ssState.SS:
                #logger.debug("handle next slowstart round")
                # re-calculate desired bandwidth - will schedule next event implicitly
                conn.updateDesiredBw(time, pRun)

            # new and entering slowstart
            elif storage.ssState == ssState.NEW:
                #logger.debug("handle handshake done - beginning slowstart")
                # re-calculate desired bandwidth - will schedule next event implicitly
                storage.ssState = ssState.SS
                conn.updateDesiredBw(time, pRun)

            # idle connection timed out
            elif storage.state == state.IDLE and storage.idleTimestamp + conn.idleTimeout >= time:
                #logger.debug("handle connection timed out - closing")
                conn.close(time, pRun)
                # no more events to be scheduled

            # broken state machine
            else:
                #logger.debug("broken TCP connection state machine:\n{s}".format(s=conn))
                assert False


    def connect(self, time, pRun):
        storage = self._storageSwitch(pRun)
        #logger.debug("connect connection {cinfo}".format(cinfo=self.getInfo()))

        # set state
        storage.state = state.IDLE

        # update error cache
        storage.lastBwUpdate = time
        storage.lastBwUpdateTransferredBytesSum = storage.transferredBytesSum

        # register with interface
        self.interface.addConnection(self, pRun)

        # register at the event simulator
        self.eventSimulator.registerTickListener(self, pRun)

        # generate slowstart event for connection setup time
        self._checkReplaceEvent(storage, time + self.handshakeDelay, "handshake delay done on connection id={id}".format(id=self.id), pRun)

        # notify others
        self._notifyNew(storage, time, pRun)


    def close(self, time, pRun):
        storage = self._storageSwitch(pRun)
        assert storage.state != state.CLOSED

        if storage.nextEvent: 
            storage.nextEvent.disableEvent(pRun)
        self.eventSimulator.unregisterTickListener(self, pRun)
        self.interface.removeConnection(self, pRun)

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
            # based on slow start state, we have to do different things
            # new connection - no need for bandwidth yet
            if storage.ssState == ssState.NEW:
                newDesiredBw = 0
            # slowstart - get from congestion window
            elif storage.ssState == ssState.SS:
                newDesiredBw = int(storage.cwnd / self.interface.getRTT())
                assert newDesiredBw != 0
            # congestion avoidance - get as much as possible
            # make sure that we don't drop below availableBw in case outstandingTransferBytesSum gets tiny
            elif storage.ssState == ssState.CA:
                newDesiredBw = max(int(storage.outstandingTransferBytesSum / self.interface.getRTT()), 1)

        # if we are idle, we need no bandwidth
        elif storage.state == state.IDLE:
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

        # only do something if bandwidth changed or if in slowstart
        if storage.availableBw != availableBw or storage.ssState == ssState.SS:
            # make sure we got no bandwidth share if we did not ask for one
            if storage.state == state.IDLE or storage.ssState == ssState.NEW:
                assert availableBw == 0
            # and get one if we need one
            elif availableBw == 0:
                logger.error("TCP connection id={id} got 0byte/s bandwidth".format(id=self.id)) 
                assert False

            # update local cache
            storage.availableBw = availableBw

            # update error cache
            storage.lastBwUpdate = time
            storage.lastBwUpdateTransferredBytesSum = storage.transferredBytesSum

            # if we are busy, we have to do different things based on slow start state
            if storage.state == state.BUSY:
                rtt = self.interface.getRTT()

                # check if we dropped out of slowstart
                if storage.ssState == ssState.SS:
                        #logger.debug("dropped out of slowstart - continue in congestion avoidence")
                    if int(storage.cwnd / rtt) > availableBw:
                        storage.ssState = ssState.CA
                        storage.cwnd = availableBw * rtt
                        # update desired bandwith to CA default or slowstart round
                        # either might fail in case of stupid co-incidence
                        storage.desiredBw = max( int(storage.outstandingTransferBytesSum / rtt), storage.desiredBw)
                    else:
                        # we did not drop out of slow start - we got what we wanted
                        # as we entedrd next round, our desired bandwitdh increased
                        pass

                # set congestion window if not in slowstart
                elif storage.ssState == ssState.CA:
                    storage.cwnd = availableBw * rtt

            # re-calculate next event
            self._scheduleNextEvent(time, pRun)


    # re-schedule event if needed
    def _checkReplaceEvent(self, storage, nextTime, description, pRun):
        assert not storage.nextEvent or type(storage.nextEvent) == TcpConnection.TransferEvent

        if storage.nextEvent and storage.nextEvent.time == nextTime and storage.nextEvent.description == description:
            return
        elif storage.nextEvent:
            storage.nextEvent.disableEvent(pRun)
            storage.nextEvent = None

        # need a new event
        storage.nextEvent = TcpConnection.TransferEvent(self, nextTime, description)
        self.eventSimulator.addEvent(storage.nextEvent, pRun)


    def _scheduleNextEvent(self, time, pRun):
        storage = self._storageSwitch(pRun)
        nextTime = None
        description = ""

        # we are idle - calculate timeout
        if storage.state == state.IDLE:
            self._checkReplaceEvent(storage, storage.idleTimestamp + self.idleTimeout, "tear down idle connection: {conn}".format(conn=self.getInfo(pRun)), pRun)

        # still in slowstart - we want to be called next in an rtt or earlier if a transfer finishes earlier
        elif storage.state == state.BUSY and storage.ssState == ssState.SS:
            transferFinishTime = storage.transfers[0].getOutstandingBytes(pRun) / storage.availableBw
            assert storage.transfers[0].getOutstandingBytes(pRun) == round(storage.availableBw*transferFinishTime)
            rtt = self.interface.getRTT()
            if transferFinishTime <= rtt:
                self._checkReplaceEvent(storage, time+transferFinishTime, "TCP id={id} transfer id={trid} finishing in slowstart".format(id=self.id, trid=storage.transfers[0].id), pRun)
                storage.currTransferFinishTime = time+transferFinishTime
            else:
                self._checkReplaceEvent(storage, time+rtt, "TCP id={id} slowstart round finishing".format(id=self.id), pRun)
        # in congestion avoidence        
        elif storage.state == state.BUSY and storage.ssState == ssState.CA:
            if storage.availableBw == 0:
                logger.error("TCP connection id={id}: state=BUSY and availableBw=0: {con}".format(id=self.id, con=self))
                assert False
            transferFinishTime = storage.transfers[0].getOutstandingBytes(pRun) / storage.availableBw
            assert storage.transfers[0].getOutstandingBytes(pRun) == round(storage.availableBw*transferFinishTime)
            self._checkReplaceEvent(storage, time+transferFinishTime, "TCP id={id} transfer finishing id={trid} in congestion avoidence".format(id=self.id, trid=storage.transfers[0].id), pRun)
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

            # based on slow start state, we have to do different things
            if storage.ssState == ssState.NEW:
                pass

            elif storage.ssState == ssState.SS:
                currTransfer.transferBytes(transferBytes, pRun)
                storage.transferredBytesSum += transferBytes
                storage.outstandingTransferBytesSum -= transferBytes
                storage.cwnd += transferBytes
    
            elif storage.ssState == ssState.CA:
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
        return "TCP id: {id} {origin} {ssl} ({state}/{ssState}) on {iface} {atrans}to go {trans}T {out}Bytes".format(id=self.id,
                                                                                    origin=self.origin,
                                                                                    ssl="(s)" if self.isSSL() else "",
                                                                                    iface=self.interface.getInfo(),
                                                                                    trans=len(storage.transfers),
                                                                                    out=storage.outstandingTransferBytesSum,
                                                                                    state=storage.state,
                                                                                    ssState=storage.ssState,
                                                                                    atrans="active transfer id={0} {1} ".format(storage.transfers[0].id if storage.transfers else "-", storage.transfers[0].getInfo() if storage.transfers else "-"))


    def __str__(self):
        return self.getInfo()


    def getSummary(self, pRun=NOPREDICT):
        storage = self._storageSwitch(pRun)
        return {'id': self.id,
                'transferredBytes': storage.transferredBytesSum,
                'transfers': [t.id for t in storage.transfers],
                'type': 'TCP',
                'interface': self.interface.description}
