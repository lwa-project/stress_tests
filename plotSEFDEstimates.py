#!/usr/bin/env python3

"""
Given a results file, plot up the SEFD estimates as a function of zenith 
angle for the observations.

Usage:
  plotSEFDEstimates.py <results file>
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
    
    ## SEFD Estimates
    colors = ['blue', 'green', 'red', 'cyan', 'magenta', 'black']
    colorIndex = 0
    colorMapping = {}
    for entry in data:
        z = float(entry['zenithAngle']) * 180.0/numpy.pi
        sefd = entry['SEFD'] / 1e3
        
        try:
            c = colorMapping[entry['name']]
        except KeyError:
            colorMapping[entry['name']] = colors[colorIndex]
            colorIndex += 1
            colorIndex %= len(colors)
            c = colorMapping[entry['name']]
        ax.plot(z, sefd, linestyle=' ', marker='o', color=c)
        ax.text(z, sefd, entry['name'])
        
    ## Custom labels
    ax.set_xlabel('Zenith Angle [$^\\circ$]')
    ax2.set_xlabel('Elevation [$^\\circ$]')
    ax.set_ylabel('SEFD [kJy]')
    
    ## Fix the elevation axis range
    xlim = ax.get_xlim()
    xlim2 = (90-xlim[0], 90-xlim[1])
    ax2.set_xlim(xlim2)
    
    plt.show()


if __name__ == "__main__":
    main(sys.argv[1:])
    
