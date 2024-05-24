#!/usr/bin/env python3

"""
Given a file containing pointing error measurements, analyze the errors 
and come up with a best-fit rotation-about-an-axis to reduce the error.
Along the way, print out various metrics about the pointing and create
a plot.

Usage:
  fitPointingError.py <results file>
"""

import os
import sys
import time
import ephem
import numpy
import argparse
from aipy import coord
from scipy.stats import pearsonr

from lsl.common import stations
from lsl.common.mcs import apply_pointing_correction

from analysis import parse, fitDataWithRotation, _rotationErrorFunction

from matplotlib import pyplot as plt


def main(args):
    # Parse the command line
    filenames = args.filename
    
    # Get the station to use
    station = stations.lwa1
    if args.lwasv:
        station = stations.lwasv
    elif args.lwana:
        try:
            observer = stations.lwana.get_observer()
        except AttributeError:
            ## Catch for older LSL
            station = stations.lwa1
            station.name = 'LWA-NA'
            station.lat, station.lon, station.elev = ('34.247', '-107.640', 2133.6)
    elif sta == 'ovrolwa':
        station = stations.lwa1
        station.name = 'OVRO-LWA'
        station.lat, station.lon, station.elev = ('37.23977727', '-118.2816667', 1183.48)
    print("Station: %s" % station.name)
    print(" ")
    
    # Load in the data
    data = []
    for filename in filenames:
        data.extend( parse(filename, station=station) )
        
    # Split by frequency
    freqs = []
    for entry in data:
        if entry['freq_MHz'] not in freqs:
            freqs.append( entry['freq_MHz'] )
    groups = {}
    for freq in freqs:
        groups[freq] = []
        for entry in data:
            if entry['freq_MHz'] == freq:
                groups[freq].append( entry )
                
    # Go!
    for freq,data in groups.items():
        if len(groups) > 1:
            print("Working on %.3f MHz" % freq)
            
        ## Initial analysis
        t0 = time.time()
        bestRMS = _rotationErrorFunction(data, 0.0, 0.0, 0.0) * 180.0/numpy.pi
        t1 = time.time()
        print("Level 0 (%.1f s):" % (t1-t0,))
        print("  Theta: None applied")
        print("  Phi:   None applied")
        print("  Psi:   None applied")
        print("  -> RMS: %.3f degrees" % bestRMS)
        
        ## Fit the pointing correction
        t0 = time.time()
        thetas = numpy.arange(0.0, 90.0, 2.0)
        phis = numpy.arange(0.0, 360.0, 2.0)
        psis = numpy.arange(-10.0, 10.0, 1.0)
        bestTheta, bestPhi, bestPsi, bestRMS = fitDataWithRotation(data, thetas, phis, psis, usePool=True)
        t1 = time.time()
        print("Level 1 (%.1f s):" % (t1-t0,))
        print("  Theta: %.1f degrees" % bestTheta)
        print("  Phi:   %.1f degrees" % bestPhi)
        print("  Psi:   %.1f degrees" % bestPsi)
        print("  -> RMS: %.3f degrees" % bestRMS)
        
        t0 = time.time()
        thetas = numpy.arange(bestTheta-4.0, bestTheta+4.0, 1.0)
        phis = numpy.arange(bestPhi-4.0, bestPhi+4.0, 1.0)
        psis = numpy.arange(bestPsi-2.0, bestPsi+2.0, 0.5)
        bestTheta, bestPhi, bestPsi, bestRMS = fitDataWithRotation(data, thetas, phis, psis, usePool=True)
        t1 = time.time()
        print("Level 2 (%.1f s):" % (t1-t0,))
        print("  Theta: %.1f degrees" % bestTheta)
        print("  Phi:   %.1f degrees" % bestPhi)
        print("  Psi:   %.1f degrees" % bestPsi)
        print("  -> RMS: %.3f degrees" % bestRMS)
        
        t0 = time.time()
        thetas = numpy.arange(bestTheta-2.0, bestTheta+2.0, 0.1)
        phis = numpy.arange(bestPhi-2.0, bestPhi+2.0, 0.1)
        psis = numpy.arange(bestPsi-1.0, bestPsi+1.0, 0.1)
        bestTheta, bestPhi, bestPsi, bestRMS = fitDataWithRotation(data, thetas, phis, psis, usePool=True)
        t1 = time.time()
        print("Level 3 (%.1f s):" % (t1-t0,))
        print("  Theta: %.1f degrees" % bestTheta)
        print("  Phi:   %.1f degrees" % bestPhi)
        print("  Psi:   %.1f degrees" % bestPsi)
        print("  -> RMS: %.3f degrees" % bestRMS)
        
        ## Plot
        fig = plt.figure()
        ax1  = fig.add_subplot(3, 1, 1)
        ax2a = fig.add_subplot(3, 2, 3)
        ax2b = fig.add_subplot(3, 2, 4)
        ax3  = fig.add_subplot(3, 1, 3)
        
        ### Figure 1 - Total pointing error as a function of zenith angle
        zeniths = []
        errors = []
        for entry in data:
            z = float(entry['zenithAngle']) * 180.0/numpy.pi
            e = ephem.separation((entry['az'],entry['el']), (entry['correctedAz'],entry['correctedEl']))
            e *= 180.0/numpy.pi
            ax1.plot(z, e, linestyle=' ', marker='^', color='blue')
            ax1.text(z, e, entry['name'])
            
            zeniths.append(z)
            errors.append(e)
        ### Figure 1 - Plot range and labels
        ax1.set_xlabel('Zenith Angle [$^\\circ$]')
        ax1.set_ylabel('Pointing Error [$^\\circ$]')
        ### Figure 1 - Report
        zeniths = numpy.array(zeniths)
        errors = numpy.array(errors)
        fit = numpy.polyfit(zeniths, errors, 1)
        print("Raw Offsets:")
        print("  Mean Error: %.3f degrees" % errors.mean())
        print("  RMS Error:  %.3f degrees" % numpy.sqrt((errors**2).mean()))
        print("  Error Slope:   %.3f degrees/degree" % fit[0])
        print("  Error R-Value: %.3f" % pearsonr(zeniths, errors)[0])
        
        ### Figure 2 (a) and 2(b) - Pointing Error broken down into RA and Dec.
        for entry in data:
            z = float(entry['zenithAngle']) * 180.0/numpy.pi
            ra = float(entry['raError']) * 12.0/numpy.pi
            dec = float(entry['decError']) * 180.0/numpy.pi
            
            ax2a.plot(z, ra*3600.0, marker='D', color='red')
            ax2a.text(z, ra*3600.0, entry['name'])
            ax2b.plot(z, dec*60.0, marker='s', color='red')
            ax2b.text(z, dec*60.0, entry['name'])
        ### Figure 2 (a) and (b) - Plot range and labels
        ax2a.set_xlabel('Zenith Angle [$^\\circ$]')
        ax2b.set_xlabel('Zenith Angle [$^\\circ$]')
        ax2a.set_ylabel('RA Error [min.]')
        ax2b.set_ylabel('Dec Error [arc min.]')
        
        ### Figure 3 - Pointing error after optimization
        zeniths = []
        errors = []
        for entry in data:
            az = float(entry['az']) * 180.0/numpy.pi
            el = float(entry['el']) * 180.0/numpy.pi
            
            azP, elP = apply_pointing_correction(az, el, bestTheta, bestPhi, bestPsi, degrees=True)
            azP = ephem.degrees(azP * numpy.pi/180.0)
            elP = ephem.degrees(elP * numpy.pi/180.0)
            
            z = float(entry['zenithAngle']) * 180.0/numpy.pi
            e = ephem.separation((entry['correctedAz'],entry['correctedEl']), (azP,elP))
            e *= 180.0/numpy.pi
            ax3.plot(z, e, linestyle=' ', marker='v', color='green')
            ax3.text(z, e, entry['name'])
            
            zeniths.append(z)
            errors.append(e)
        ### Figure 3 - Plot range and labels
        ax3.set_xlabel('Zenith Angle [$^\\circ$]')
        ax3.set_ylabel('Pointing Error [$^\\circ$]')
        ### Figure 3 - Report
        zeniths = numpy.array(zeniths)
        errors = numpy.array(errors)
        fit = numpy.polyfit(zeniths, errors, 1)
        print("Corrected Offsets:")
        print("  Mean Error: %.3f degrees" % errors.mean())
        print("  RMS Error:  %.3f degrees" % numpy.sqrt((errors**2).mean()))
        print("  Error Slope:   %.3f degrees/degree" % fit[0])
        print("  Error R-Value: %.3f" % pearsonr(zeniths, errors)[0])
        
        fig.tight_layout()
        
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='script that takes a text file containing pointing measurments and fits a rotation to the data',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument('filename', type=str, nargs='+',
                        help='text file to analyze')
    sgroup = parser.add_mutually_exclusive_group(required=False)
    sgroup.add_argument('-v', '--lwasv', action='store_true',
                        help='use LWA-SV instead of LWA1 if the station is not specified in the HDF5 file')
    sgroup.add_argument('-n', '--lwana', action='store_true',
                        help='use LWA-NA instead of LWA1 if the station is not specified in the HDF5 file')
    sgroup.add_argument('-o', '--ovrolwa', action='store_true',
                        help='use OVRO-LWA instead of LWA1 if the station is not specified in the HDF5 file')
    args = parser.parse_args()
    main(args)
    
