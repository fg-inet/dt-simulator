#!/bin/bash
# scan datasets in the folder "workload" and generate job lists for distribution to multiple compute servers
# by Philipp S. Tiesel
#
# usage: 	ln -s dtsimulator/scripts/* .
#			mkdir workload
#			-> put each dataset in a separeate folder, these may contain as many subfolders as you like
#			-> adapt TODO below to match your distribution needs
#			./mkjobs.sh

mkdir jobs
for dir in $(cd workload ; find . -type d | sed 's/^\.\///')
do
	echo "generating jobs for $dir"
	mkdir -p results/$dir
	dtsimulator/scripts/generateTasks.py dtsimulator/src/mainSingle.py workload/$dir results/$dir > "jobs/job.$(sed 's/\//_/g' <<< $dir ).in"
done
echo "concatinating and splitting jobs"
(	cd jobs ; 
	cat job.*.in | split -a 3 -l 1000 - jobpart. ;
	find . | grep 'jobpart\.' | sort -R > jobparts
	# TODO: adjust splitting to run jobs on multiple machines
	jobparts | xargs cat > jobs.$(hostname)
	# head -n 6000 jobparts | xargs cat > jobs.gonzales
	# tail -n +6001 jobparts | xargs cat > jobs.speedy
	xargs rm < jobparts
)
echo "now distribute the jobs to the hosts and use \"runjobs \$(hostanme)\" to get the work done" 
