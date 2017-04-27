#!/usr/bin/env python3
import sys
import os
import glob

bwIf1  = [500, 2,   6, 12, 20, 50]
bwIf2  = [500, 5,  20, 50]
rttIf1 = [10, 20,  30, 50]
rttIf2 = [20, 50, 100, 200]

if len(sys.argv) != 4:
    sys.stderr.write("Usage: generateTasks.py <simulator-program (e.g. \"mainSingle.py\"> <har-folder> <results-folder>\n")
    sys.stderr.write("Note: the generated tasks will be printed to stdout!\n")
    sys.exit(-1)

resultsDir = sys.argv[3]

if not os.path.isdir(resultsDir):
    sys.stderr.write("Error: results dir does not exist!\n")
    sys.exit(-1)

for filename in glob.glob(sys.argv[2]+"/*.har"):
    outputDir = "{res_base}/{res_dir}".format(res_dir=os.path.basename(filename), res_base=resultsDir)
    os.makedirs(outputDir)
    for bw1 in bwIf1:
        for bw2 in bwIf2:
            for rtt1 in rttIf1:
                for rtt2 in rttIf2:
                    policies = ["only1-1", "only1-2", "rr-1", "eaf", "mptcp", "mptcp-1", "eaf-mptcp"]
                    for policy in policies:
                        print("python3.4 {code} {mul1} {bw1} {rtt1} {mul2} {bw2} {rtt2} {pol} {file_} {outputDir}/{fileOut}_{mul1}{bw1}_{rtt1}-{mul2}{bw2}_{rtt2}_{pol}.sim.json 2> {outputDir}/{fileOut}_{mul1}{bw1}_{rtt1}-{mul2}{bw2}_{rtt2}_{pol}.err > {outputDir}/{fileOut}_{mul1}{bw1}_{rtt1}-{mul2}{bw2}_{rtt2}_{pol}.csv".format(fileOut=filename.split("/")[-1], code=sys.argv[1], mul1='k' if bw1 >= 100 else 'm', bw1=bw1, rtt1=rtt1, mul2='k' if bw2 >= 100 else 'm', bw2=bw2, rtt2=rtt2, pol=policy, file_=filename, outputDir=outputDir))

