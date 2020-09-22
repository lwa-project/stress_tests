#!/usr/bin/env python3

"""
Given one or more HDF5 files associated with observations generated by 
generateRun.py, determine the current pointing offset and estimate the SEFD
and FWHM.
"""

import os
import sys
import aipy
import h5py
import ephem
import numpy
import argparse
from datetime import datetime
from scipy.optimize import leastsq

from lsl import astro
from lsl.common import stations
from lsl.statistics import robust

from analysis import getSources, getAIPYSources, fitDriftscan, fitDecOffset

from matplotlib import pyplot as plt


SIDEREAL_DAY = 86164.090530833	# seconds


def smartMod(x, y):
    try:
        pos = numpy.where( x >= y/2 )
        while len(pos[0]):
            x[pos] -= y
            pos = numpy.where( x >= y/2 )
        neg = numpy.where( x <= -y/2 )
        while len(neg[0]):
            x[neg] += y
            neg = numpy.where( x <= -y/2 )
            
    except (TypeError, IndexError):
        while x >= y:
            x -= y
        while x <= -y:
            x += y
            
    return x


def func(p, x):
    if len(p) == 4:
        height = p[0]
        center = p[1]
        width  = p[2]
        offset = p[3]
    else:
        height = p[0]
        center = p[1]
        width  = 2.0
        offset = p[2]
    
    y = height*numpy.exp(-4*numpy.log(2)*(x - center)**2/width**2 ) + offset
    return y


def err(p, x, y):
    yFit = func(p, x)
    return y - yFit 


def main(args):
    filenames = args.filename
    
    # Read in each of the data sets and sum the polarizations
    data = {}
    pointing = {}
    tStartPlot = 1e12
    for filename in filenames:
        h = h5py.File(filename, 'r')
        try:
            sta = h.attrs['StationName']
        except KeyError:
            sta = None
        obs = h.get('Observation1', None)
        name = obs.attrs['ObservationName']
        try:
            name = name.decode()
        except AttributeError:
            pass
        pointing[name] = obs.attrs['TargetName']
        try:
            pointing[name] = pointing[name].decode()
        except AttributeError:
            pass
            
        tuning1 = obs.get('Tuning1', None)
        tuning2 = obs.get('Tuning2', None)
        
        t = obs['time'][:]
        f1 = tuning1['freq'][:]
        I1 = tuning1['XX'][:,:] + tuning1['YY'][:,:]
        f2 = tuning2['freq'][:]
        I2 = tuning2['XX'][:,:] + tuning2['YY'][:,:]
        
        if t[0] < tStartPlot:
            tStartPlot = t[0]
        
        data[name] = {'t': t, 'f1': f1, 'I1': I1, 'f2': f2, 'I2': I2}
        h.close()
    
    # Get the site
    if sta in (None, ''):
        observer = stations.lwa1.get_observer()
        if args.lwasv:
            observer = stations.lwasv.get_observer()
    else:
        try:
            sta = sta.decode()
        except AttributeError:
            pass
        if sta == 'lwa1':
            print("Data appears to be from LWA1")
            observer = stations.lwa1.get_observer()
        elif sta == 'lwasv':
            print("Data appears to be from LWA-SV")
            observer = stations.lwasv.get_observer()
        else:
            raise RuntimeError("Unknown LWA station name: %s" % sta)
            
    # Load in the sources and find the right one
    srcs = getSources()
    simSrcs = getAIPYSources()
        
    toUse = None
    for srcName in data.keys():
        for src in srcs.keys():
            if src.lower() == srcName.lower():
                toUse = src
                observer.date = datetime.utcfromtimestamp( data[srcName]['t'][0] )
                break;
    if toUse is None:
        raise RuntimeError("Unknown source in input files")
        
    toUseAIPY = srcs[toUse].name
    try:
        simSrcs[toUseAIPY]
    except KeyError:
        toUseAIPY = None
        print("Warning: Cannot find flux for this target")
        
    # Find out when the source should have transitted the beam
    tTransit = 0.0
    zenithAngle = ephem.degrees('180:00:00')
    for name in pointing.keys():
        if name.lower() != srcs[toUse].name.lower():
            continue
            
        junk1, az, junk2, junk3, el, junk4 = pointing[name].split(None, 5)
        az = ephem.degrees(az)
        el = ephem.degrees(el)
        
        bestT = 0.0
        bestV = 1e6
        for t in data[name]['t']:
            observer.date = datetime.utcfromtimestamp(t).strftime("%Y/%m/%d %H:%M:%S")
            srcs[toUse].compute(observer)
            
            sep = ephem.separation((srcs[toUse].az, srcs[toUse].alt), (az,el))
            if sep < bestV:
                bestT = t
                bestV = sep
    tTransit = bestT
    observer.date = datetime.utcfromtimestamp(tTransit).strftime("%Y/%m/%d %H:%M:%S")
    zenithAngle = ephem.degrees(ephem.degrees('90:00:00') - el)
    
    # Plot
    fig = plt.figure()
    fig.suptitle('LWA1' if sta == 'lwa1' else 'LWA-SV')
    ax1 = fig.add_subplot(1, 2, 1)
    ax2 = fig.add_subplot(1, 2, 2)
    
    raOffsets1 = {}
    decPowers1 = {}
    fwhmEstimates1 = {}
    sefdEstimate1 = None
    
    raOffsets2 = {}
    decPowers2 = {}
    fwhmEstimates2 = {}
    sefdEstimate2 = None
    for name in data.keys():
        t = data[name]['t']
        f1 = data[name]['f1']
        I1 = data[name]['I1']
        f2 = data[name]['f2']
        I2 = data[name]['I2']
        
        # Select data that was actually recorded
        good = numpy.where( (t > 0) & (I1[:,10] > 0) & (I2[:,10] > 0) )[0][:-1]
        t = t[good]
        I1 = I1[good,:]
        I2 = I2[good,:]
        
        # Sum over the inner 75% of the band
        toUseSpec = range(f1.size//8, 7*f1.size//8)
        I1 = I1[:,toUseSpec].sum(axis=1)
        I2 = I2[:,toUseSpec].sum(axis=1)
        
        # Select "good" data
        bad1 = []
        bad2 = []
        for i in range(0, I1.size-201):
            start = i
            stop = start + 201
            
            try:
                m1 = robust.mean(I1[start:stop])
                s1 = robust.std( I1[start:stop])
                reject = numpy.where( numpy.abs(I1[start:stop] - m1) > 4*s1 )[0]
                for b in reject:
                    bad1.append( b + start )
            except:
                continue
            try:
                m2 = robust.mean(I2[start:stop])
                s2 = robust.std( I2[start:stop])
                reject = numpy.where( numpy.abs(I2[start:stop] - m2) > 4*s2 )[0]
                for b in reject:
                    bad2.append( b + start )
            except:
                continue
                
        for b in bad1:
            try:
                I1[b] = robust.mean(I1[b-10:b+10])
            except:
                pass
        for b in bad2:
            try:
                I2[b] = robust.mean(I2[b-10:b+10])
            except:
                pass
        
        # Convert the scales to unit flux
        I1 /= I1.max()
        I2 /= I2.max()
        
        # Fit a Gaussian to the power to find the transit time and beam width
        includeLinear = False
        if includeLinear:
            obsTransit1, sefdMetric1, obsFWHM1, obsSlope1, obsFit1 = fitDriftscan(t, I1, includeLinear=True)
            obsTransit2, sefdMetric2, obsFWHM2, obsSlope2, obsFit2 = fitDriftscan(t, I2, includeLinear=True)
            
            linear1 = obsSlope1 * t
            linear1 -= linear1[:10].mean()
            linear2 = obsSlope2 * t
            linear2 -= linear2[:10].mean()
            
            I1 -= linear1
            obsFit1 -= linear1
            I2 -= linear2
            obsFit2 -= linear2
            
        obsTransit1, sefdMetric1, obsFWHM1, obsFit1 = fitDriftscan(t, I1, includeLinear=False)
        obsTransit2, sefdMetric2, obsFWHM2, obsFit2 = fitDriftscan(t, I2, includeLinear=False)
        
        # Save the results
        diff1 = obsTransit1 - tTransit
        raOffsets1[name] = smartMod(diff1, SIDEREAL_DAY)
        decPowers1[name] = obsFit1.max() - obsFit1.min()
        fwhmEstimates1[name] = obsFWHM1/3600.*15.*numpy.cos(srcs[toUse]._dec)
        
        diff2 = obsTransit2 - tTransit
        raOffsets2[name] = smartMod(diff2, SIDEREAL_DAY)
        decPowers2[name] = obsFit2.max() - obsFit2.min()
        fwhmEstimates2[name] = obsFWHM2/3600.*15.*numpy.cos(srcs[toUse]._dec)
        
        # Report
        print('Target: %s' % name)
        print('  Tuning 1 @ %.2f MHz' % (f1.mean()/1e6,))
        print('    FWHM: %.2f s (%.2f deg)' % (obsFWHM1, obsFWHM1/3600.*15.*numpy.cos(srcs[toUse]._dec)))
        print('    Observed Transit: %s' % datetime.utcfromtimestamp(obsTransit1))
        print('    Expected Transit: %s' % datetime.utcfromtimestamp(tTransit))
        print('    -> Difference: %.2f s' % diff1)
        if toUseAIPY is None:
            print('    1/(P1/P0 - 1): %.3f' % sefdMetric1)
        else:
            try:
                simSrcs[toUseAIPY].compute(observer, afreqs=f1.mean()/1e9)
                srcFlux = simSrcs[toUseAIPY].jys
            except TypeError:
                f0, index, Flux0 = simSrcs[toUseAIPY].mfreq, simSrcs[toUseAIPY].index, simSrcs[toUseAIPY]._jys
                srcFlux = Flux0 * (f1.mean()/1e9 / f0)**index
            sefd = srcFlux*sefdMetric1 / 1e3
            print('    S / (P1/P0 - 1): %.3f kJy' % sefd)
            if name == srcs[toUse].name:
                sefdEstimate1 = sefd*1e3
                
        print('  Tuning 2 @ %.2f MHz' % (f2.mean()/1e6,))
        print('    FWHM: %.2f s (%.2f deg)' % (obsFWHM2, obsFWHM2/3600.*15.*numpy.cos(srcs[toUse]._dec)))
        print('    Observed Transit: %s' % datetime.utcfromtimestamp(obsTransit2))
        print('    Expected Transit: %s' % datetime.utcfromtimestamp(tTransit))
        print('    -> Difference: %.2f s' % diff2)
        if toUseAIPY is None:
            print('    1/(P1/P0 - 1): %.3f' % sefdMetric2)
        else:
            try:
                simSrcs[toUseAIPY].compute(observer, afreqs=f1.mean()/1e9)
                srcFlux = simSrcs[toUseAIPY].jys
            except TypeError:
                f0, index, Flux0 = simSrcs[toUseAIPY].mfreq, simSrcs[toUseAIPY].index, simSrcs[toUseAIPY]._jys
                srcFlux = Flux0 * (f2.mean()/1e9 / f0)**index
            sefd = srcFlux*sefdMetric2 / 1e3
            print('    S / (P1/P0 - 1): %.3f kJy' % sefd)
            if name == srcs[toUse].name:
                sefdEstimate2 = sefd*1e3
        print(' ')
        
        # Plot
        ax1.plot(smartMod(t-tStartPlot, SIDEREAL_DAY), I1, label="%s" % name)
        ax1.plot(smartMod(t-tStartPlot, SIDEREAL_DAY), obsFit1, linestyle=':')

        ax2.plot(smartMod(t-tStartPlot, SIDEREAL_DAY), I2, label="%s" % name)		
        ax2.plot(smartMod(t-tStartPlot, SIDEREAL_DAY), obsFit2, linestyle=':')
        
    ylim1 = ax1.get_ylim()
    ax1.vlines(tTransit-tStartPlot, *ylim1, linestyle='--', label='Expected Transit')
    ax1.set_ylim(ylim1)
    ax1.legend(loc=0)
    ax1.set_title('%.2f MHz' % (f1.mean()/1e6,))
    ax1.set_xlabel('Elapsed Time [s]')
    ax1.set_ylabel('Power [arb.]')
    
    ylim2 = ax2.get_ylim()
    ax2.vlines(tTransit-tStartPlot, *ylim2, linestyle='--', label='Expected Transit')
    ax2.set_ylim(ylim2)
    ax2.legend(loc=0)
    ax2.set_title('%.2f MHz' % (f2.mean()/1e6,))
    ax2.set_xlabel('Elapsed Time [s]')
    ax2.set_ylabel('Power [arb.]')
    
    # Compute the dec. offset
    dataSet1 = (f1.mean(), raOffsets1, decPowers1, fwhmEstimates1, sefdEstimate1)
    dataSet2 = (f2.mean(), raOffsets2, decPowers2, fwhmEstimates2, sefdEstimate2)

    sys.stderr.write("Source YYYY/MM/DD HH:MM:SS MHz    Z          errRA      errDec      SEFD      FWHM\n")
    for f,raOffsets,decPowers,fwhmEstimates,sefdEstimate in (dataSet1, dataSet2):
        do = []
        dp = []
        bestOffset = None
        bestPower = -1e6
        bestFWHM = None
        for name in decPowers.keys():
            offset = raOffsets[name]
            power = decPowers[name]
            fwhm = fwhmEstimates[name]
        
            if power > bestPower:
                bestOffset = offset
                bestPower = power
                bestFWHM = fwhm
            
            if name.lower().find('north') != -1:
                do.append(1.0)
            elif name.lower().find('south') != -1:
                do.append(-1.0)
            else:
                do.append(0.0)
            dp.append(power)
        
        do = numpy.array(do)
        dp = numpy.array(dp)
        order = numpy.argsort(do)
        do = do[order]
        dp = dp[order]
    
        try:
            decOffset = fitDecOffset(do, dp, fwhm=bestFWHM)
        except TypeError:
            decOffset = -99
        
        raOffset = ephem.hours('00:00:%f' % bestOffset)
        decOffset = ephem.degrees('%f' % decOffset)
        fwhmEstimate = ephem.degrees('%f' % bestFWHM)
        print("%-6s %-19s %6.3f %-10s %-10s %-10s %10.3f %-10s" % (srcs[toUse].name, datetime.utcfromtimestamp(tTransit).strftime("%Y/%m/%d %H:%M:%S"), f/1e6, zenithAngle, raOffset, decOffset, sefdEstimate, fwhmEstimate))

    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='given one or more HDF5 files associated with observations generated by generateRun.py, determine the current pointing offset and estimate the SEFD and FWHM',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument('filename', type=str, nargs='+', 
                        help='HDF5 file to analyze')
    parser.add_argument('-v', '--lwasv', action='store_true',
                        help='use LWA-SV instead of LWA1 if the station is not specified in the HDF5 file')
    args = parser.parse_args()
    main(args)
    
