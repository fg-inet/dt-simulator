#!/usr/bin/env python3
""" Verify whether timing in .har file and simulated timings are sound """

import sys, os
import logging
from itertools import chain

from simulator.globals import *
from simulator.transferManager import *
from simulator.interface import Interface
from simulator.policy import *
from harParser import HarParser
from simulator.eventSimulator import NOPREDICT


__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logging.getLogger("main")
logging.disable(logging.DEBUG)

def childTimingSum(transfer, parentTime):
    durationCandidate = 0
    #logger.debug("children of: {0}".format(transfer.getInfo()))
    for child in transfer.children:
        childrenDuration = child.objectTimings['connect'] + child.objectTimings['wait'] + child.objectTimings['receive']# + child.objectTimings['dns'] + child.objectTimings['blocked'] + child.objectTimings['send']
        #logger.debug("child: {0} + parent: {1} = {2}".format(childrenDuration, parentTime, childrenDuration + parentTime))
        childrenDuration += childTimingSum(child, childrenDuration + parentTime)
        
        if childrenDuration > durationCandidate:
            durationCandidate = childrenDuration

    #logger.debug("children of: {1} return longest candidate: {0}".format(durationCandidate, transfer.id))
    return durationCandidate


def searchForRttEstimate(harOrigin, fileName):
    with open(fileName) as fh:
        for entry in fh:
            logger.debug(entry)
            if harOrigin == entry.split('+')[0]:
                return float(entry.split(' ')[1])
    return None


if __name__ == "__main__":
    if len(sys.argv) < 4:
        logger.error("Usage: <bw in Mbit> <rtt in milliseconds> <harfile>")
        sys.exit(-1)

    bw = mbit(float(sys.argv[1]))
    # rtt = ms(float(sys.argv[2]))
    ifileName = sys.argv[3]

    infileSite, infileDate, infileTime = ifileName[:-4].split('+')

    transferManager = TransferManager()
    fh = open(ifileName)
    h = HarParser(fh, transferManager, verification=True)
    h.generateTransfers()
    fh.close()

    actualDuration = 0
    for transfer in transferManager.transfers:
        if transfer.isEnabled(NOPREDICT):
            #logger.debug("root: {0}".format(transfer.getInfo()))

            durationCandidate = transfer.objectTimings['connect'] + transfer.objectTimings['wait'] + transfer.objectTimings['receive']# + transfer.objectTimings['dns'] + transfer.objectTimings['blocked'] + transfer.objectTimings['send']
            #logger.debug("durationCandidate: {0}".format(durationCandidate))

            durationCandidate += childTimingSum(transfer, durationCandidate)            

            if durationCandidate > actualDuration:
                actualDuration = durationCandidate

            #logger.debug("actualDuration: {0}".format(actualDuration))

    rtt = searchForRttEstimate(h.origin, sys.argv[2])
    if not rtt:
        logger.error("Could not find RTT estimate - skipping")
        sys.exit(-1)
    else:
        rtt = ms(rtt)

    interface = Interface(rtt=rtt, bandwidth=bw, description="if1")
    policy = useOneInterfaceOnly(interface)

    (result, time) = transferManager.runTransfers([interface], policy)

    #"website", "crawl", "actual-time", "simulator-time"
    print(",".join(map(lambda s: str(s), [h.origin, infileDate, actualDuration, time])))
