#!/usr/bin/env python3 
import sys
import os
import re

if len(sys.argv) != 4:
    sys.stderr.write("Usage: find results -type f -name \*.csv -size 0 | rerunTasks.py <simulator-program (e.g. \"mainSingle.py\"> <har-folder> <results-folder>\n")
    sys.stderr.write("Note: the generated tasks will be printed to stdout!\n")
    sys.exit(-1)

workloadDir = sys.argv[2]
resultsDir = sys.argv[3]

if not os.path.isdir(resultsDir):
    sys.stderr.write("Error: results dir does not exist!\n")
    sys.exit(-1)

job_re=re.compile(".har_([^.+]*)\.csv")
job_split=re.compile("[-_]")

for line in sys.stdin:
    lp = line.rstrip('\n').split("/")
    har="/".join(lp[1:4])
    job=job_split.split(job_re.search(lp[4]).group(1), 4)
    outputDir = "{res_base}/{res_dir}".format(res_dir=har, res_base=resultsDir)
    filename="{workloadDir}/{har}".format(workloadDir=workloadDir, har=har)

    print("python3.4 {code} {mul1} {bw1} {rtt1} {mul2} {bw2} {rtt2} {pol} {file_} {outputDir}/{fileOut}_{mul1}{bw1}_{rtt1}-{mul2}{bw2}_{rtt2}_{pol}.sim.json 2> {outputDir}/{fileOut}_{mul1}{bw1}_{rtt1}-{mul2}{bw2}_{rtt2}_{pol}.err > {outputDir}/{fileOut}_{mul1}{bw1}_{rtt1}-{mul2}{bw2}_{rtt2}_{pol}.csv".format(fileOut=os.path.basename(har), code=sys.argv[1], mul1=job[0][0], bw1=job[0][1:], rtt1=job[1], mul2=job[2][0], bw2=job[2][1:], rtt2=job[3], pol=job[4], file_=filename, outputDir=outputDir))

