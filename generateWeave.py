#!/usr/bin/env python3

"""
Script to generate a basket weave SDF for a pointing/sensitivity check.

Usage:
  generateWeave.py [OPTIONS] <source name> YYYY/MM/DD HH:MM:SS[.SS]
"""

import os
import sys
import ephem
import numpy
import argparse
from datetime import datetime, timedelta

from lsl.common import stations
from lsl.common import sdf
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
        
    # Read in the arguments
    if args.source is None or args.date is None or args.time is None:
        raise RuntimeError("Need a source name and a UTC date/time")
    srcName = args.source
    date = "%s %s" % (args.date, args.time)
    date = date.replace('-', '/')
    subSecondSplit = date.rfind('.')
    if subSecondSplit != -1:
        date = date[:subSecondSplit]
        
    # Get the site and set the date
    observer = stations.lwa1.get_observer()
    if args.lwasv:
        observer = stations.lwasv.get_observer()
    elif args.lwana:
        observer = stations.lwana.get_observer()
    elif args.ovrolwa:
        station = stations.lwa1
        station.name = 'OVRO-LWA'
        station.lat, station.lon, station.elev = ('37.23977727', '-118.2816667', 1182.89)
        observer = station.get_observer()
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
    ## Scale for whether or not it is a mini-station
    pm_range = 8.0 if args.ministation else 4.0
    ## First, declination
    for offset in numpy.linspace(-pm_range, pm_range, 17):
        pnts.append( (src._ra, ephem.degrees(src._dec+offset*numpy.pi/180)) )
    #pnts.extend(pnts)
    ## Now, RA
    for offset in numpy.linspace(-pm_range, pm_range, 17):
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
    if args.lwasv:
        beam  = 1									## Beam to use
        spc   = [1024, 1536]						## Spectrometer setup
        flt   = 7									## DRX filter code
        tstep = timedelta(seconds=6, microseconds=0)	## Date step between the pointings
        
    # Setup the times
    midPoint = datetime.strptime(date, "%Y/%m/%d %H:%M:%S")
    start = midPoint - len(pnts)//2*tstep
    
    # Print out where we are at
    print("Start of observations: %s" % start)
    print("Mid-point of observation: %s" % midPoint)
    print(" ")
    
    # Make the SDF
    observer = sdf.Observer("Jayce Dowell", 99)
    session = sdf.Session("Pointing Weave Session Using %s" % srcs[toUse].name, args.session_id)
    project = sdf.Project(observer, "DRX Pointing Weave", "COMST", [session,])
    project.sessions[0].drx_beam = beam
    project.sessions[0].spcSetup = spc
    project.sessions[0].logScheduler = False
    project.sessions[0].logExecutive = False
    if args.ucf_username is not None:
        project.sessions[0].data_return_method = 'UCF'
        project.sessions[0].ucf_username = args.ucf_username
        
    obs = sdf.Stepped(src.name, "Az: %.1f degrees; El: %.1f degrees" % (az, el), start.strftime("UTC %Y/%m/%d %H:%M:%S"), flt, is_radec=True)
    for i,(ra,dec) in enumerate(pnts):
        d = tstep
        stp = sdf.BeamStep(ra, dec, d, args.freqs[0], args.freqs[1], is_radec=True)
        obs.append(stp)
    project.sessions[0].observations.append(obs)
    
    sdfName = 'COMST_%s_%s_%s_B%i.sdf' % (start.strftime("%y%m%d"), start.strftime("%H%M"), src.name, beam)
    s = project.render()
    fh = open(sdfName, 'w')
    fh.write(s)
    fh.close()
    print('->', sdfName)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='script to generate a basketweave SDFs for testing the pointing',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument('source', type=str, nargs='?', 
                        help='source name to generate run for')
    parser.add_argument('date', type=aph.date, nargs='?',
                        help='UTC date for the run as YYYY/MM/DD')
    parser.add_argument('time', type=aph.time, nargs='?',
                        help='UTC time for the run as HH:MM:SS[.SS]')
    sgroup = parser.add_mutually_exclusive_group(required=False)
    sgroup.add_argument('-v', '--lwasv', action='store_true',
                        help='compute for LWA-SV instead of LWA1')
    sgroup.add_argument('-n', '--lwana', action='store_true',
                        help='compute for LWA-NA instead of LWA1')
    sgroup.add_argument('-o', '--ovrolwa', action='store_true',
                        help='compute for OVRO-LWA instead of LWA1')
    parser.add_argument('-m', '--ministation', action='store_true',
                        help='setup a run for a mini-station instead of a full station')
    parser.add_argument('-f', '--freqs', type=aph.positive_float, nargs=2, default=[37.9, 74.03],
                        help='center frequencies for the two tunings in MHz')
    parser.add_argument('-l', '--list', action='store_true',
                        help='list valid source names and exit')
    parser.add_argument('-s', '--session-id', type=int, default=1001,
                        help='session ID to use')
    parser.add_argument('-u', '--ucf-username', type=str,
                        help='optional UCF username for data copy')
    args = parser.parse_args()
    args.freqs[0] *= 1e6
    args.freqs[1] *= 1e6
    main(args)
    
