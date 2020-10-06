#!/usr/bin/env python3

"""
Given a results file, plot up the FWHM estimates as a function of zenith 
angle for the observations.

Usage:
  plotFWHMEstimates.py <results file>
"""

import os
import sys
import ephem
import numpy
from aipy import coord

from analysis import parse

from matplotlib.ticker import NullFormatter
from matplotlib import pyplot as plt


def main(args):
    filename = args[0]
    
    # Load in the data
    data = parse(filename)
    
    # Plot
    fig = plt.figure()
    ax = fig.gca()
    ax2 = ax.twiny()
    
    ## FWHM Estimates
    colors = ['blue', 'green', 'red', 'cyan', 'magenta', 'black']
    colorIndex = 0
    colorMapping = {}
    for entry in data:
        z = float(entry['zenithAngle']) * 180.0/numpy.pi
        fwhm = float(entry['FWHM']) * 180.0/numpy.pi
        if fwhm < 0:
            continue
            
        try:
            c = colorMapping[entry['name']]
        except KeyError:
            colorMapping[entry['name']] = colors[colorIndex]
            colorIndex += 1
            colorIndex %= len(colors)
            c = colorMapping[entry['name']]
        ax.plot(z, fwhm, linestyle=' ', marker='o', color=c)
        ax.text(z, fwhm, entry['name'])
        
    ## Custom labels
    ax.set_xlabel('Zenith Angle [$^\\circ$]')
    ax2.set_xlabel('Elevation [$^\\circ$]')
    ax.set_ylabel('FWHM [$^\\circ$]')
    
    ## Fix the elevation axis range
    xlim = ax.get_xlim()
    xlim2 = (90-xlim[0], 90-xlim[1])
    ax2.set_xlim(xlim2)
    
    plt.show()


if __name__ == "__main__":
    main(sys.argv[1:])
    
