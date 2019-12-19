#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script to generate a collection of SDFs to for a pointing/sensitivity check.

Usage:
  generateRun.py [OPTIONS] <source name> YYYY/MM/DD HH:MM:SS[.SS]

$Rev$
$LastChangedBy$
$LastChangedDate$
"""

import os
import sys
import numpy
import ephem
import getopt
from datetime import datetime, timedelta

from lsl.common import stations
from lsl.common import sdf

from analysis import getSources


def usage(exitCode=None):
    print """generateRun.py - Script to generate a collection of SDFs to for a pointing/
sensitivity check.

Usage: generateRun.py [OPTIONS] SourceName YYYY/MM/DD HH:MM:SS[.SS]

Options:
-h, --help                  Display this help information
-v, --lwassv                Compute for LWA-SV instead of LWA-1
-l, --list                  List valid sources and exit
-d, --duration              Observation length in seconds (Default = 7200)
-t, --target-only           Generate the SDF for the target source only 
                            (Default = generate target plus north and south
                            offsets)
-s, --session-id            Comma separated list of session IDs to use 
                            (Default = 1001, 1002, 1003)
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
    config['duration'] = 7200
    config['sessionID'] = [1001,1002,1003]
    config['targetOnly'] = False
    
    # Read in and process the command line flags
    try:
        opts, args = getopt.getopt(args, "hvld:ts:", ["help", "lwasv", "list", "duration=", "target-only", "session-id="])
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
        elif opt in ('-d', '--duration'):
            config['duration'] = int(float(value))
        elif opt in ('-t', '--target-only'):
            config['targetOnly'] = True
        elif opt in ('-s', '--session-id'):
            config['sessionID'] = [int(v) for v in value.split(',')]
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
    srcs[toUse].compute(observer)
    
    # Calculate the offset pointings
    northPointing = ephem.FixedBody()
    northPointing.name = "Offset to the north"
    northPointing._ra  = srcs[toUse]._ra
    northPointing._dec = srcs[toUse]._dec + ephem.degrees('1:00:00')
    northPointing.compute(observer)
    
    southPointing = ephem.FixedBody()
    southPointing.name = "Offset to the south"
    southPointing._ra  = srcs[toUse]._ra
    southPointing._dec = srcs[toUse]._dec - ephem.degrees('1:00:00')
    southPointing.compute(observer)
    
    # Setup the times
    midPoint = datetime.strptime(date, "%Y/%m/%d %H:%M:%S")
    start = midPoint - timedelta(seconds=config['duration']/2)
    
    # Print out where we are at
    print "Start of observations: %s" % start
    print "Mid-point of observation: %s" % midPoint
    print " "
    
    # Setup to deal with out LWA-SV is
    beams   = (2,3,4)								## Beams to use
    targets = (srcs[toUse], northPointing, southPointing)	## Target list
    spc     = [1024, 6144]							## Spectrometer setup
    flt     = 7									## DRX filter code
    tstep   = timedelta(0)							## Date step between the pointings
    if config['site'] == 'lwasv':
        beams   = (1,1,1)								## Beams to use
        targets = (srcs[toUse], northPointing, southPointing)	## Target list
        spc     = [1024, 3072]							## Spectrometer setup
        flt     = 6									## DRX filter code
        tstep   = timedelta(seconds=86164, microseconds=90531)	## Date step between the pointings
        
    
    # Make the SDFs
    sdfCount = 0
    for beam,target in zip(beams, targets):
        if config['targetOnly'] and target != srcs[toUse]:
            continue
            
        az = round(target.az*180.0/numpy.pi, 1) % 360.0
        el = round(target.alt*180.0/numpy.pi, 1)
        sdfName = 'COMJD_%s_%s_%s_%i.sdf' % (start.strftime("%y%m%d"), start.strftime("%H%M"), srcs[toUse].name, beam)
        
        print "Source: %s" % target.name
        print "  Az: %.1f" % az
        print "  El: %.1f" % el
        print "  Beam: %i" % beam
        print "  SDF: %s" % sdfName
        
        observer = sdf.Observer("Jayce Dowell", 99)
        session = sdf.Session("Pointing Check Session Using %s" % srcs[toUse].name, config['sessionID'][sdfCount % len(config['sessionID'])])
        project = sdf.Project(observer, "DRX Pointing Checking", "COMJD", [session,])
        project.sessions[0].drxBeam = beam
        project.sessions[0].spcSetup = spc
        project.sessions[0].logScheduler = False
        project.sessions[0].logExecutive = False
        
        obs = sdf.Stepped(target.name, "Az: %.1f degrees; El: %.1f degrees" % (az, el), start.strftime("UTC %Y/%m/%d %H:%M:%S"), flt, RADec=False)
        stp = sdf.BeamStep(az, el, str(config['duration']), 37.9e6, 74.03e6, RADec=False)
        obs.append(stp)
        project.sessions[0].observations.append(obs)
        
        s = project.render()
        fh = open(sdfName, 'w')
        fh.write(s)
        fh.close()
        
        sdfCount += 1
        start += tstep


if __name__ == "__main__":
    main(sys.argv[1:])
    
