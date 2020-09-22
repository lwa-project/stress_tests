#!/usr/bin/env python

"""
Script to generate a basket weave SDF for a pointing/sensitivity check.

Usage:
  generateWeave.py [OPTIONS] <source name> YYYY/MM/DD HH:MM:SS[.SS]
"""

from __future__ import division

import os
import sys
import ephem
import numpy
import getopt
from datetime import datetime, timedelta

from lsl.common import stations
from lsl.common import sdf

from analysis import getSources


def usage(exitCode=None):
    print """generateWeave.py - Script to generate a basketweave SDFs for testing the pointing.

Usage: generateWeave.py [OPTIONS] SourceName YYYY/MM/DD HH:MM:SS[.SS]

Options:
-h, --help                  Display this help information
-v, --lwassv                Compute for LWA-SV instead of LWA-1
-l, --list                  List valid sources and exit
-s, --session-id            Session IDs to use (Default = 1001)
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
    config['sessionID'] = 1001
    
    # Read in and process the command line flags
    try:
        opts, args = getopt.getopt(args, "hvls:", ["help", "lwasv", "list", "session-id="])
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
        elif opt in ('-l', '--list'):
            config['list'] = True
        elif opt in ('-t', '--target-only'):
            config['targetOnly'] = True
        elif opt in ('-s', '--session-id'):
            config['sessionID'] = int(value, 10)
        else:
            assert False
            
    # Add in arguments
    config['args'] = args
    
    # Validate the arguments
    config['args'] = args
    if not config['list'] and len(config['args']) != 3:
        raise RuntimeError("Must specify a source name and a UTC date/time")
        
    # Return configuration
    return config


def main(args):
    # Parse the command line
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
        
    # Read in the arguments
    srcName = config['args'][0]
    date = "%s %s" % (config['args'][1], config['args'][2])
    date = date.replace('-', '/')
    subSecondSplit = date.rfind('.')
    if subSecondSplit != -1:
        date = date[:subSecondSplit]
        
    # Get the site and set the date
    observer = stations.lwa1.get_observer()
    if config['site'] == 'lwasv':
        observer = stations.lwasv.get_observer()
    observer.date = date
    
    # Find the right source
    toUse = None
    for src in srcs.keys():
        if src.lower() == srcName.lower():
            toUse = src
    if toUse is None:
        raise RuntimeError("Unknown source '%s'" % srcName)
        
    # Calculate the position of the source at transit
    src = srcs[toUse]
    src.compute(observer)
    az = round(src.az*180.0/numpy.pi, 1) % 360.0
    el = round(src.alt*180.0/numpy.pi, 1)
    
    # Come up with the pattern
    pnts = []
    ## First, declination
    for offset in numpy.linspace(-4.0, 4.0, 17):
        pnts.append( (src._ra, ephem.degrees(src._dec+offset*numpy.pi/180)) )
    #pnts.extend(pnts)
    ## Now, RA
    for offset in numpy.linspace(-4.0, 4.0, 17):
        offset = offset / numpy.cos(src.dec)
        pnts.append( (ephem.hours(src._ra+offset*numpy.pi/180), src._dec) )
    #pnts.extend(pnts)
    ## Finally the reference pointings
    refs = [(src._ra,src._dec) for pnt in pnts]
    ## Interleave
    pnts = [(r,p) for p,r in zip(pnts,refs)]
    pnts = [p for pair in pnts for p in pair]
    
    # Setup to deal with out LWA-SV is
    beam  = 2									## Beam to use
    spc   = [1024, 1536]						## Spectrometer setup
    flt   = 7									## DRX filter code
    tstep = timedelta(seconds=6, microseconds=0)	## Date step between the pointings
    if config['site'] == 'lwasv':
        beam  = 1									## Beam to use
        spc   = [1024, 1536]						## Spectrometer setup
        flt   = 7									## DRX filter code
        tstep = timedelta(seconds=6, microseconds=0)	## Date step between the pointings
        
    # Setup the times
    midPoint = datetime.strptime(date, "%Y/%m/%d %H:%M:%S")
    start = midPoint - len(pnts)//2*tstep
    
    # Print out where we are at
    print "Start of observations: %s" % start
    print "Mid-point of observation: %s" % midPoint
    print " "
    
    # Make the SDF
    observer = sdf.Observer("Jayce Dowell", 99)
    session = sdf.Session("Pointing Weave Session Using %s" % srcs[toUse].name, config['sessionID'])
    project = sdf.Project(observer, "DRX Pointing Weave", "COMST", [session,])
    project.sessions[0].drx_beam = beam
    project.sessions[0].spcSetup = spc
    project.sessions[0].logScheduler = False
    project.sessions[0].logExecutive = False
    
    obs = sdf.Stepped(src.name, "Az: %.1f degrees; El: %.1f degrees" % (az, el), start.strftime("UTC %Y/%m/%d %H:%M:%S"), flt, is_radec=True)
    for i,(ra,dec) in enumerate(pnts):
        d = tstep
        stp = sdf.BeamStep(ra, dec, d, 37.9e6, 74.03e6, is_radec=True)
        obs.append(stp)
    project.sessions[0].observations.append(obs)
    
    sdfName = 'COMST_%s_%s_%s_B%i.sdf' % (start.strftime("%y%m%d"), start.strftime("%H%M"), src.name, beam)
    s = project.render()
    fh = open(sdfName, 'w')
    fh.write(s)
    fh.close()
    print '->', sdfName


if __name__ == "__main__":
    main(sys.argv[1:])
    
