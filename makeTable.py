#!/usr/bin/env python

"""
Given a file containing results of a pointing check, convert the data to a
LaTeX table suitable for the "LWA1 Pointing Error and Correction" memo.

Usage:
  makeTable.py <results file>
"""

import sys

from analysis import parse


def main(args):
    filename = args[0]
    
    # Load in the data
    data = parse(filename)
    
    # Table Header
    print "\\begin{tabular}{|c|c|r|r|r|r|r|}"
    print "\\hline"
    print "Source Name & UTC Observation Midpoint & Azimuth & Elevation & RA Error & Dec. Error & SEFD\\\\"
    print "~ & [YYYY/MM/DD HH:MM:SS] & [DDD:MM.SS.S] & [DD:MM:SS.S] & [HH:MM:SS.SS] & [DD:MM:SS.S] & [kJy] \\\\"
    print "\\hline"
    print "\\hline"
    
    # Table Contents
    for entry in data:
        sefd = float(entry['SEFD'])/1e3
        print "%-5s & %s & %11s & %11s & %11s & %11s & %4.1f\\\\" % (entry['name'], entry['date'], entry['az'], entry['el'], entry['raError'], entry['decError'], sefd)
        
    # Table Close and Caption
    print "\\hline"
    print "\\end{tabular}"
    print "\\caption[Right Ascension and Declination Pointing Errors]{\\label{tab:obs}List of Drift Scan Sets used to Determine the Pointing Error}"


if __name__ == "__main__":
    main(sys.argv[1:])
    
