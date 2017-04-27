""" simple event simulator 

this simulator can be switched into predictions mode and can return to last non-prediction state any time

"""

import logging
from heapq import *
from copy import copy

__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


# logging format setup
logging.basicConfig(format='[{levelname:<6}]{filename:>20}.{funcName:<24}l{lineno:>3} {message}', style='{', level="DEBUG")

# we are not running in prediction mode
NOPREDICT = -1

class timeLogAdapter:

    class CustomAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            if self.extra['time'] == None:
                return "---- no sim ---- {msg}".format(msg=msg), kwargs
            elif self.extra['pRun'] == NOPREDICT:
                return "p=real t={time:3.4f}s {msg}".format(time=self.extra['time'], msg=msg), kwargs
            else:
                return "p={pRun:>4d} t={time:3.4f}s {msg}".format(pRun=self.extra['pRun'], time=self.extra['time'], msg=msg), kwargs


    def __init__(self):
        self.extra = {'time': None, 'pRun': NOPREDICT}


    def updateTime(self, time, pRun):
        self.extra['time'] = time
        self.extra['pRun'] = pRun


    def setup(self, name):
        logger = logging.getLogger(name)
        logger = timeLogAdapter.CustomAdapter(logger, self.extra)
        return logger


# print simulator time in logging messages - setup
logAdapter = timeLogAdapter()
logger = logAdapter.setup("eventSimulator")


class TickListener(object):

    def _tickTime(self, start, end, pRun):
        pass

    def tickTime(self, start, end, pRun):
        self._tickTime(start, end, pRun)



class Event(object):

    def __init__(self, time, description=""):
        self.time = time
        self.rDisabled = False
        self.pDisabled = False
        self.pRun = NOPREDICT
        self.description = description


    def __eq__(self, other):
        return self.time == other.time


    def __lt__(self, other):
        return self.time < other.time


    def _handleEvent(self, eventSimulator, time, pRun):
        pass


    def handleEvent(self, eventSimulator, time, pRun):
        #logger.debug("handling event: {0}".format(self.description))
        self._handleEvent(eventSimulator, time, pRun)


    def disableEvent(self, pRun):
        if pRun == NOPREDICT:
            self.rDisabled = True
        else:
            self.pRun = pRun
            self.pDisabled = True

    def isDisabled(self, pRun):

        if pRun != self.pRun:
            self.pDisabled = self.rDisabled
            self.pRun = pRun

        if   pRun == NOPREDICT and not self.rDisabled:
            return False
        elif pRun != NOPREDICT and not self.pDisabled:
            return False
        else:
            return True


    def __str__(self):
        return "time: {0}s desc: {1}".format(self.time, self.description)



class EventSimulator(object):
    
    # container to hold state that might be changed during prediction runs
    class EventSimulatorStorage(object):

        def __init__(self):
            self.time = 0.0
            self.pRun = NOPREDICT
            self.eventQueue = []
            self.tickListener = []

        def clone(self):
            clone = copy(self)
            clone.eventQueue   = self.eventQueue[:]
            clone.tickListener = self.tickListener[:]
            return clone


    def __init__(self):
        # state for real execution
        self.rStorage = EventSimulator.EventSimulatorStorage()

        # state for current prediction run
        self.pStorage = None

        # serial number of current prediction run
        self.pRun = NOPREDICT
        self.pRunLast = -1

        # fix logging
        logAdapter.updateTime(self.rStorage.time, self.rStorage.pRun)



    def _storageSwitch(self, pRun):
        assert pRun == self.pRun

        if pRun == NOPREDICT:
            return self.rStorage
        else:
            return self.pStorage


    def beginPrediction(self):
        assert self.pRun == NOPREDICT

        # fix prun state
        self.pStorage = self.rStorage.clone()
        self.pStorage.pRun = self.pRunLast + 1
        self.pRun = self.pStorage.pRun

        # fix logging
        logAdapter.updateTime(self.pStorage.time, self.pStorage.pRun)

        return self.pRun


    def endPrecition(self, pRun):
        assert pRun == self.pRun

        self.pRunLast = self.pRun
        self.pRun = NOPREDICT

        #logger.debug("marking pRun={pRun} as finished - might have some stragglers on call stack".format(pRun=pRun))


    def getTime(self, pRun):
        assert self.pRun == pRun

        storage = self._storageSwitch(pRun)
        return storage.time


    def addEvent(self, event, pRun = NOPREDICT):
        #logger.debug("adding Event: {1}".format(event))

        if pRun != self.pRun:
            assert pRun != NOPREDICT
            #logger.debug("ignoring straggler event from finished pRun")
        else:
            storage = self._storageSwitch(pRun)
            heappush(storage.eventQueue, event)


    def registerTickListener(self, tickListener, pRun = NOPREDICT):
        storage = self._storageSwitch(pRun)
        storage.tickListener.append(tickListener)   


    def unregisterTickListener(self, tickListener, pRun = NOPREDICT):
        storage = self._storageSwitch(pRun)
        storage.tickListener.remove(tickListener)


    def _tickTime(self, storage, eventTime, nextEventTime, pRun):
        #logger.debug("ticking time from {start:.6f}s to {end:.6f}s".format(start=eventTime, end=nextEventTime))
        for tickListener in storage.tickListener:
            tickListener.tickTime(eventTime, nextEventTime, pRun)
        logAdapter.updateTime(nextEventTime, pRun)


    def _run(self, storage, pRun):
        assert storage.eventQueue
        assert self.pRun == pRun

        # main simulator run
        while self.pRun == pRun and storage.eventQueue:
            assert storage.pRun == pRun

            # get next event
            event = heappop(storage.eventQueue)
            if event.isDisabled(pRun):
                continue

            # tick time if time changed
            if event.time > storage.time:
                self._tickTime(storage, storage.time, event.time, pRun)

            # handle event
            assert storage.time <= event.time
            storage.time = event.time
            event.handleEvent(self, event.time, pRun)

        #logger.debug("finished simulator loop")


    def realRun(self):
        assert self.rStorage.time == 0

        storage = self.rStorage
        self._run(storage, NOPREDICT)


    def predictionRun(self, pRun):
        assert self.pRun == pRun

        storage = self.pStorage
        self._run(storage, pRun)

        # fix logging
        logAdapter.updateTime(self.rStorage.time, self.pRun)



if __name__ == "__main__":
    #logger.debug("testing ticklistenerclass")
    t = TickListener(None)
    #logger.debug("testing eventclass")
    e = Event(0.0, "test")
    #logger.debug("testing eventSimulatorclass")
    es = EventSimulator()
    es.beginPrediction()
    #logger.debug("test prediction")
