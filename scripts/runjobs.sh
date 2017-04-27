#!/bin/sh
if [ -z "$1" -o "$1" = "-h" ]
then
	echo "usage: $0 \$(hostname)"
	echo "	will execute all jobs in jobs/jobs.\$(hostname) using gnu parallel"
	echo "	use \"./jobfails.sh -v \$(hostname).joblog to analyze failed simulator runs"
else
	parallel --nice 10 --joblog joblog.$1 --resume --progress :::: jobs/jobs.$1
fi
