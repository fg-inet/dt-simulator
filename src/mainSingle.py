#!/usr/bin/env python3
""" run a simulation using in the data transfer simulator 

usage: mainSingle.py (m|k} <bw1> <rtt1> (m|k} <bw2> <rtt2> <policy> <har-file> <json output>

the simulation result is printed to sys.stdout, log and errors are printed to sys.stderr
"""

import sys, os
import logging
from itertools import chain

from simulator.globals import *
from simulator.transferManager import *
from simulator.interface import Interface
from simulator.policy import *
from harParser import HarParser


__author__ = "Mirko Palmer <mirko@inet.tu-berlin.de>, Philipp S. Tiesel <philipp@inet.tu-berlin.de>"
__copyright__ = "Copyright 2017, FG INET, TU Berlin"
__license__ = "RELAXED CRAPL v0 BETA 1"


logger = logging.getLogger("main")
logging.disable(logging.DEBUG)

def simulatorRun(ifileName, origin, transferManager, policy, interfaces, oFile):

    (infileSite, infileDate, infileTime) = ifileName[:-4].split('+')

    print('--- next simulator run ---', file=progressFH)
    print('{h:<16s}{p}'.format(h="policy", p=policy.getInfo()), file=progressFH)
    h = "interfaces:"
    for i in interfaces:
        print('{h:<16s}{i}'.format(h=h, i=i.getInfo()), file=progressFH)
        h = ""
    (result, time) = transferManager.runTransfers(interfaces, policy)
    print('\n{h:<16s}{t:3.3f}s\n\n'.format(h="result:", t=time), end="", file=progressFH, flush=True)

    # print simple output to stdout
    #"website", "crawl", "time", "policy", "if1_bw", "if1_rtt", "if2_bw", "if2_rtt", "time"
    print( ",".join(map(lambda s: str(s), [origin, infileDate, infileTime, policy.getInfo()] + list(chain.from_iterable( map(lambda i: [i.bandwidth, i.rtt], interfaces))) + [time])))

    # dump simulator as json object
    result.dumpJson(oFile)


if __name__ == "__main__":
    bw1 = None
    if sys.argv[1] == 'm':
        bw1 = mbit(float(sys.argv[2]))
    else:
        bw1 = kbit(float(sys.argv[2]))

    rtt1 = ms(float(sys.argv[3]))

    bw2 = None
    if sys.argv[4] == 'm':
        bw2 = mbit(float(sys.argv[5]))
    else:
        bw2 = kbit(float(sys.argv[5]))

    rtt2 = ms(float(sys.argv[6]))

    policyStr = sys.argv[7]

    ifileName = sys.argv[8]
    if sys.argv[9]:
        oFile = open(sys.argv[9], 'w')
    else:
        oFilePrefix = os.path.basename(ifileName[:-4]+".result")
        oFile = open("{pfx}.sim.json".format(pfx=oFilePrefix), 'w')


    transferManager = TransferManager()
    fh = open(ifileName)
    h = HarParser(fh, transferManager)
    h.generateTransfers()
    fh.close()

    oFile.write('{"simulatorResults": [\n')


    interfaces = [Interface(rtt=rtt1, bandwidth=bw1, description="if1"),
                  Interface(rtt=rtt2, bandwidth=bw2, description="if2")]

    policies = {"only1-1": useOneInterfaceOnly(interfaces[0]), 
                "only1-2": useOneInterfaceOnly(interfaces[1]), 
                "rr-1": roundRobin(interfaces), 
                "rr-2": roundRobin([interfaces[1], interfaces[0]]), 
                "eaf": earliestArrivalFirst(),
                "mptcp": mptcpFullMeshPolicy(),
                "mptcp-1": mptcpFullMeshIFListPolicy(interfaces),
                "eaf-mptcp": earliestArrivalFirstMPTCP()}

    #print("simulatorRun({ifileName}, {origin}, -, {policy}, {interfaces}, {oFilePrefix})".format(ifileName=ifileName, origin=h.origin, policy=policy.getInfo(), interfaces=[i.getInfo() for i in interfaces], oFilePrefix=oFilePrefix))
    simulatorRun(ifileName, h.origin, transferManager, policies
        [policyStr], interfaces, oFile)
    oFile.write(',\n')

    oFile.write("{}]}")
    oFile.close()
