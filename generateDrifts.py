#!/usr/bin/env python3

"""
Script to generate a collection of SDFs to for a pointing/sensitivity check.

Usage:
  generateRun.py [OPTIONS] <source name> YYYY/MM/DD HH:MM:SS[.SS]
"""

import os
import sys
import numpy
import ephem
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
    if args.lwana:
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
        station.lat, station.lon, station.elev = ('37.23977727', '-118.2816667', 1183.48)
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
    start = midPoint - timedelta(seconds=args.duration/2)
    
    # Print out where we are at
    print("Start of observations: %s" % start)
    print("Mid-point of observation: %s" % midPoint)
    print(" ")
    
    # Setup to deal with how LWA-SV is
    beams   = (2,3,4)								## Beams to use
    targets = (srcs[toUse], northPointing, southPointing)	## Target list
    spc     = [1024, 6144]							## Spectrometer setup
    flt     = 7									## DRX filter code
    tstep   = timedelta(0)							## Date step between the pointings
    if args.lwasv:
        beams   = (1,1,1)								## Beams to use
        targets = (srcs[toUse], northPointing, southPointing)	## Target list
        spc     = [1024, 6144]							## Spectrometer setup
        flt     = 7									## DRX filter code
        tstep   = timedelta(seconds=86164, microseconds=90531)	## Date step between the pointings
        
    
    # Make the SDFs
    sdfCount = 0
    for beam,target in zip(beams, targets):
        if args.target_only and target != srcs[toUse]:
            continue
            
        az = round(target.az*180.0/numpy.pi, 1) % 360.0
        el = round(target.alt*180.0/numpy.pi, 1)
        sdfName = 'COMST_%s_%s_%s_B%i.sdf' % (start.strftime("%y%m%d"), start.strftime("%H%M"), srcs[toUse].name, beam)
        
        print("Source: %s" % target.name)
        print("  Az: %.1f" % az)
        print("  El: %.1f" % el)
        print("  Beam: %i" % beam)
        print("  SDF: %s" % sdfName)
        
        observer = sdf.Observer("Jayce Dowell", 99)
        session = sdf.Session("Pointing Check Session Using %s" % srcs[toUse].name, args.session_id[sdfCount % len(args.session_id)])
        project = sdf.Project(observer, "DRX Pointing Checking", "COMST", [session,])
        project.sessions[0].drx_beam = beam
        project.sessions[0].spc_setup = spc
        project.sessions[0].logScheduler = False
        project.sessions[0].logExecutive = False
        if args.ucf_username is not None:
            project.sessions[0].data_return_method = 'UCF'
            project.sessions[0].ucf_username = args.ucf_username
            
        obs = sdf.Stepped(target.name, "Az: %.1f degrees; El: %.1f degrees" % (az, el), start.strftime("UTC %Y/%m/%d %H:%M:%S"), flt, is_radec=False)
        stp = sdf.BeamStep(az, el, str(args.duration), args.freqs[0], args.freqs[1], is_radec=False)
        obs.append(stp)
        project.sessions[0].observations.append(obs)
        
        s = project.render()
        fh = open(sdfName, 'w')
        fh.write(s)
        fh.close()
        
        sdfCount += 1
        start += tstep


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='script to generate a collection of SDFs to for a pointing/sensitivity check',
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
    parser.add_argument('-f', '--freqs', type=aph.positive_float, nargs=2, default=[37.9, 74.03],
                        help='center frequencies for the two tunings in MHz')
    parser.add_argument('-l', '--list', action='store_true',
                        help='list valid source names and exit')
    parser.add_argument('-d', '--duration', type=float, default=7200.0,
                        help='observation length in seconds')
    parser.add_argument('-t', '--target-only', action='store_true',
                        help='only generate the SDF for the target source')
    parser.add_argument('-s', '--session-id', type=aph.csv_int_list, default=[1001,1002,1003],
                        help='comma separated list of session IDs to use')
    parser.add_argument('-u', '--ucf-username', type=str,
                        help='optional UCF username for data copy')
    args = parser.parse_args()
    args.freqs[0] *= 1e6
    args.freqs[1] *= 1e6
    
    while len(args.session_id) < 3:
        args.session_id.append(args.session_id[-1]+1)
        
    main(args)
    
