#!/usr/bin/env python3

"""
Script to generate a list of times that a given source is at a variety of 
elevations (30 to 90 degrees, plus transit) for a given UTC day.

Usage:
  observationTimes.py <source name> YYYY/MM/DD
"""

import sys
import ephem
import numpy
import argparse
from datetime import datetime

from lsl.common import stations
from lsl.misc import parser as aph

from analysis import getSources


def main(args):
    # Load in the sources and list if needed
    srcs = getSources()
    if args.list:
        print("Valid Sources:")
        print(" ")
        print("%-8s  %11s  %11s  %6s" % ("Name", "RA", "Dec", "Epoch"))
        print("-"*42)
        for nm,src in srcs.items():
            print("%-8s  %11s  %11s  %6s" % (src.name, src._ra, src._dec, src._epoch.tuple()[0]))
        sys.exit()
        
    # Break out what we need from the arguments
    srcName = args.source
    date    = args.date
    if srcName is None or date is None:
        raise RuntimeError("Need both a source name and a UTC date")
        
    # Find the right source
    toUse = None
    for src in srcs.keys():
        if src.lower() == srcName.lower():
            toUse = src
            
    # Get the observer
    observer = stations.lwa1.get_observer()
    if args.lwasv:
        observer = stations.lwasv.get_observer()
    elif args.lwasv:
        try:
            observer = stations.lwana.get_observer()
        except AttributeError:
            ## Catch for older LSL
            station = stations.lwa1
            station.name = 'LWA-NA'
            station.lat, station.lon, station.elev = ('34.247', '-107.640', 2133.6)
            observer = station.get_observer()
    elif args.ovrolwa:
        station = stations.lwa1
        station.name = 'OVRO-LWA'
        station.lat, station.lon, station.elev = ('37.23977727', '-118.2816667', 1182.89)
        observer = station.get_observer()
        
    if toUse is None:
        raise RuntimeError("Cannot find source '%s'" % srcName)
        
    observer.date = "%s 00:00:00.000000" % date
    
    tRise = {}
    tSet = {}
    for el in args.elevations:
        ## Reset the data and horizon
        observer.date = "%s 00:00:00.000000" % date
        observer.horizon = el
        
        ## Rise time
        try:
            rt = observer.next_rising(srcs[toUse])
            if int(rt)-observer.date > 1:
                rt = observer.prev_rising(srcs[toUse])
            tRise[el] = rt
        except ephem.CircumpolarError:
            continue
            
        ## Set time
        try:
            st = observer.next_setting(srcs[toUse])
            if int(st)-observer.date > 1:
                st = observer.prev_setting(srcs[toUse])
            tSet[el] = st
        except ephem.CircumpolarError:
            continue
            
    # Reset the data and get the transit time
    observer.date = "%s 00:00:00.000000" % date
    tTransit = observer.next_transit(srcs[toUse])
    if tTransit - observer.date > 1:
        tTransit = observer.prev_transit(srcs[toUse])
        
    # Report - rising then setting
    print("%s on %s UTC:" % (srcs[toUse].name, date))
    
    print("  rising")
    for el in args.elevations:
        try:
            t = tRise[el]
            observer.date = t
            srcs[toUse].compute(observer)
            
            print("    el: %4.1f degrees at %s (el: %4.1f, az: %5.1f)" % (el*180/numpy.pi, t, srcs[toUse].alt*180/numpy.pi, srcs[toUse].az*180/numpy.pi))
        except KeyError:
            pass
            
    print("  transit")
    observer.date = tTransit
    srcs[toUse].compute(observer)
    print("    el: %4.1f degrees at %s" % (srcs[toUse].alt*180/numpy.pi, tTransit))
    
    print("  setting")
    for el in args.elevations[::-1]:
        try:
            t = tSet[el]
            observer.date = t
            srcs[toUse].compute(observer)
            
            print("    el: %4.1f degrees at %s (el: %4.1f, az: %5.1f)" % (el*180/numpy.pi, t, srcs[toUse].alt*180/numpy.pi, srcs[toUse].az*180/numpy.pi))
        except KeyError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='script to generate a list of times that a given source is at a variety of elevations (30 to 90 degrees, plus transit) for a given UTC day',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument('source', type=str, nargs='?',
                        help='source name to compute times for')
    parser.add_argument('date', type=aph.date, nargs='?',
                        help='UTC date to compute times for')
    sgroup = parser.add_mutually_exclusive_group(required=False)
    sgroup.add_argument('-v', '--lwasv', action='store_true',
                        help='compute for LWA-SV instead of LWA1')
    sgroup.add_argument('-n', '--lwana', action='store_true',
                        help='compute for LWA-NA instead of LWA1')
    sgroup.add_argument('-o', '--ovrolwa', action='store_true',
                        help='compute for OVRO-LWA instead of LWA1')
    parser.add_argument('-l', '--list', action='store_true',
                        help='list valid source names and exit')
    parser.add_argument('-e', '--elevations', type=aph.csv_degrees_list, default=[ephem.degrees('%i' % v) for v in range(30, 100, 10)],
                        help='comma separated list of additional elevations in degrees to search for')
    args = parser.parse_args()
    main(args)
    
