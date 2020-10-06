#!/usr/bin/env python3

"""
Given a results file, plot up the sky coverage for the observations.

Usage:
  plotSkyCoverage.py <results file>
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
    ax2 = ax.twinx()
    ax3 = ax.twiny()
    
    ## Source positions across the sky
    colors = ['blue', 'green', 'red', 'cyan', 'magenta', 'black']
    colorIndex = 0
    colorMapping = {}
    for entry in data:
        top = coord.azalt2top((entry['az'], entry['el']))
        
        try:
            c = colorMapping[entry['name']]
        except KeyError:
            colorMapping[entry['name']] = colors[colorIndex]
            colorIndex += 1
            colorIndex %= len(colors)
            c = colorMapping[entry['name']]
        ax.plot(top[0], top[1], linestyle=' ', marker='o', color=c)
        ax.text(top[0], top[1], entry['name'])
        
    ## Horizon and lines of constant elevation
    for el in (0, 20, 40, 60, 80):
        tops = []
        for az in xrange(0, 362, 2):
            tops.append( coord.azalt2top((az*numpy.pi/180, el*numpy.pi/180)) )
        tops = numpy.array(tops)
        if el == 0:
            ls = '-'
        else:
            ls = ':'
        ax.plot(tops[:,0], tops[:,1], linestyle=ls, color='black')
        
    ## No tick marks
    ax.xaxis.set_major_formatter( NullFormatter() )
    ax.yaxis.set_major_formatter( NullFormatter() )
    
    ## Custom labels
    ax.xaxis.set_ticks((-1, 0, 1))
    ax.xaxis.set_ticklabels(('', 'S', ''))
    ax.yaxis.set_ticks((-1, 0, 1))
    ax.yaxis.set_ticklabels(('', 'E', ''))
    
    ax2.yaxis.set_ticks((-1, 0, 1))
    ax2.yaxis.set_ticklabels(('', 'W', ''))
    
    ax3.xaxis.set_ticks((-1, 0, 1))
    ax3.xaxis.set_ticklabels(('', 'N', ''))
    
    ## Plot range
    for a in (ax, ax2, ax3):
        a.set_aspect('equal')
        a.set_xlim((1,-1))
        a.set_ylim((-1,1))
        
    plt.show()


if __name__ == "__main__":
    main(sys.argv[1:])
    
