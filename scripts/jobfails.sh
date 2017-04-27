#!/bin/bash
# parse gnu parallel joblog file and display simulator runs with non-zero exit code
# also show stderr of them when -v is present
# By Philipp S. Tiesel
#
# Usage: ./jobfails.sh $(hostname).joblog

if [ "$1" = "-v" ]
then
    awk '$7!=0{ gsub(/\\/, ""); 
                printf("\n--- %s: %s%s %s %s%s %s %s\n", $22, $15, $16, $17, $18, $19, $20, $21);  
                while ((getline line < $25) > 0) {printf("\t%s\n", line)} }' $2
else
    awk '$7!=0{ gsub(/\\/, ""); 
                printf("%s: %s%s %s %s%s %s %s\n", $22, $15, $16, $17, $18, $19, $20, $21); }' $1
fi
