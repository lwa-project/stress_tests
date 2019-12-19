#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script to generate a list of times that a given source is at a variety of 
elevations (30 to 90 degrees, plus transit) for a given UTC day.

Usage:
  observationTimes.py <source name> YYYY/MM/DD

$Rev$
$LastChangedBy$
$LastChangedDate$
"""

import sys
import ephem
import numpy
import getopt
from datetime import datetime

from lsl.common import stations

from analysis import getSources


def usage(exitCode=None):
    print """observationTimes.py - Script to generate a list of times that a given 
source is at a variety of elevations (30 to 90 degrees, plus transit) for 
a given UTC day.

Usage:
observationTimes.py [OPTIONS] <source name> YYYY/MM/DD

Options:
-h, --help                  Display this help information
-v, --lwassv                Compute for LWA-SV instead of LWA-1
-l, --list                  List valid sources and exit
-e, --elevations            Comma separated list of additional 
                            elevations in degrees to search for
"""

    if exitCode is not None:
        sys.exit(exitCode)
    else:
        return True


def parseOptions(args):
    config = {}
    # Command line flags - default values
    config['site'] = 'lwa1'
    config['list'] = False
    config['elevations'] = [30, 40, 50, 60, 70, 80, 90]
    
    # Read in and process the command line flags
    try:
        opts, args = getopt.getopt(args, "hvle:", ["help", "lwasv", "list", "elevations="])
    except getopt.GetoptError, err:
        # Print help information and exit:
        print str(err) # will print something like "option -a not recognized"
        usage(exitCode=2)
        
    # Work through opts
    for opt, value in opts:
        if opt in ('-h', '--help'):
            usage(exitCode=0)
        elif opt in ('-v', '--lwasv'):
            config['site'] = 'lwasv'
        elif opt in ('-e', '--elevations'):
            fields = value.split(',')
            fields = [float(f) for f in fields]
            for f in fields:
                if f not in config['elevations']:
                    config['elevations'].append(f)
        elif opt in ('-l', '--list'):
            config['list'] = True
        else:
            assert False
            
    # Add in arguments and make sure there are enough
    config['args'] = args
    if not config['list'] and len(config['args']) != 2:
        raise RuntimeError("Must specify a source name and UTC date")
        
    # Sort the list of elevations
    config['elevations'].sort()
    
    # Return configuration
    return config


def main(args):
    # Parse command line options
    config = parseOptions(args)
    
    # Load in the sources and list if needed
    srcs = getSources()
    if config['list']:
        print "Valid Sources:"
        print " "
        print "%-8s  %11s  %11s  %6s" % ("Name", "RA", "Dec", "Epoch")
        print "-"*42
        for nm,src in srcs.iteritems():
            print "%-8s  %11s  %11s  %6s" % (src.name, src._ra, src._dec, src._epoch.tuple()[0])
        sys.exit()
        
    # Break out what we need from the arguments
    srcName = config['args'][0]
    date    = config['args'][1]
    
    # Find the right source
    toUse = None
    for src in srcs.keys():
        if src.lower() == srcName.lower():
            toUse = src
            
    # Get the observer
    obs = stations.lwa1.get_observer()
    if config['site'] == 'lwasv':
        obs = stations.lwasv.get_observer()
        
    if toUse is None:
        raise RuntimeError("Cannot find source '%s'" % srcName)
        
    obs.date = "%s 00:00:00.000000" % date
    
    tRise = {}
    tSet = {}
    for el in config['elevations']:
        ## Reset the data and horizon
        obs.date = "%s 00:00:00.000000" % date
        obs.horizon = ephem.degrees(str(el))
        
        ## Rise time
        try:
            rt = obs.next_rising(srcs[toUse])
            if int(rt)-obs.date > 1:
                rt = obs.prev_rising(srcs[toUse])
            tRise[el] = rt
        except ephem.CircumpolarError:
            continue
            
        ## Set time
        try:
            st = obs.next_setting(srcs[toUse])
            if int(st)-obs.date > 1:
                st = obs.prev_setting(srcs[toUse])
            tSet[el] = st
        except ephem.CircumpolarError:
            continue
            
    # Reset the data and get the transit time
    obs.date = "%s 00:00:00.000000" % date
    tTransit = obs.next_transit(srcs[toUse])
    if tTransit - obs.date > 1:
        tTransit = obs.prev_transit(srcs[toUse])
        
    # Report - rising then setting
    print "%s on %s UTC:" % (srcs[toUse].name, date)
    
    print "  rising"
    for el in config['elevations']:
        try:
            t = tRise[el]
            obs.date = t
            srcs[toUse].compute(obs)
            
            print "    el: %4.1f degrees at %s (el: %4.1f, az: %5.1f)" % (el, t, srcs[toUse].alt*180/numpy.pi, srcs[toUse].az*180/numpy.pi)
        except KeyError:
            pass
            
    print "  transit"
    obs.date = tTransit
    srcs[toUse].compute(obs)
    print "    el: %4.1f degrees at %s" % (srcs[toUse].alt*180/numpy.pi, tTransit)
    
    print "  setting"
    for el in config['elevations'][::-1]:
        try:
            t = tSet[el]
            obs.date = t
            srcs[toUse].compute(obs)
            
            print "    el: %4.1f degrees at %s (el: %4.1f, az: %5.1f)" % (el, t, srcs[toUse].alt*180/numpy.pi, srcs[toUse].az*180/numpy.pi)
        except KeyError:
            pass


if __name__ == "__main__":
    main(sys.argv[1:])
    
