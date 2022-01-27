#!/usr/bin/env python3

"""
Given one or more HDF5 files associated with observations generated by 
generateWeave.py, determine the current pointing offset and estimate the
SEFD and FWHM.
"""

import os
import sys
import aipy
import h5py
import ephem
import numpy
import argparse
import operator
from datetime import datetime
from scipy.optimize import leastsq
from scipy.interpolate import interp1d

from astropy.time import Time as AstroTime

from lsl import astro
from lsl.common import stations
from lsl.statistics import robust

from analysis import getSources, getAIPYSources, fitDriftscan, fitDecOffset

from matplotlib import pyplot as plt


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
    
    finalResults = []
    for filename in filenames:
        # Read in each of the data sets and sum the polarizations
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
        rpos = obs.attrs['TargetName']
        try:
            rpos = rpos.decode()
        except AttributeError:
            pass
            
        pnt = obs.get('Pointing', None)
        stp = pnt['Steps'][:,:]
        
        tuning1 = obs.get('Tuning1', None)
        tuning2 = obs.get('Tuning2', None)
        if tuning2 is None:
            tuning2 = tuning1
            
        t = obs['time'][:]
        try:
            fmt = obs['time'].attrs['format']
            scl = obs['time'].attrs['scale']
            try:
                fmt = fmt.decode()
                scl = scl.decode()
            except AttributeError:
                pass
                
            if fmt != 'unix' or scl != 'utc':
                t = [AstroTime(*v, format=fmt, scale=scl) for v in t]
                t = [v.utc.unix for v in t]
                t = numpy.array(t)
                
            else:
                t = t["int"] + t["frac"]
        except (KeyError, ValueError):
            pass
        f1 = tuning1['freq'][:]
        f2 = tuning2['freq'][:]
        try:
            I1 = numpy.sqrt(tuning1['XY_real'][:,:]**2 + tuning1['XY_imag'][:,:]**2)
            I2 = numpy.sqrt(tuning2['XY_real'][:,:]**2 + tuning2['XY_imag'][:,:]**2)
        except KeyError:
            try:
                I1 = tuning1['I'][:,:]
                I2 = tuning2['I'][:,:]
            except KeyError:
                I1 = tuning1['XX'][:,:] + tuning1['YY'][:,:]
                I2 = tuning2['XX'][:,:] + tuning2['YY'][:,:]
                
        h.close()
        
        # Get the site
        if sta in (None, ''):
            sta = 'lwa1'
            observer = stations.lwa1.get_observer()
            if args.lwasv:
                sta = 'lwasv'
                observer = stations.lwasv.get_observer()
        else:
            try:
                sta = sta.decode()
            except AttributeError:
                pass
            if sta == 'lwa1':
                print("Data appears to be from LWA1")
                sta_name = 'LWA1'
                observer = stations.lwa1.get_observer()
            elif sta == 'lwasv':
                print("Data appears to be from LWA-SV")
                sta_name = 'LWA-SV'
                observer = stations.lwasv.get_observer()
            elif sta == 'ovrolwa':
                print("Data appears to be from OVRO-LWA")
                sta_name = 'OVRO-LWA'
                station = stations.lwa1
                station.name = 'OVRO-LWA'
                station.lat, station.lon, station.elev = ('37.23977727', '-118.2816667', 1182.89)
                observer = station.get_observer()
            else:
                raise RuntimeError("Unknown LWA station name: %s" % sta)
                
        # Load in the sources and find the right one
        srcs = getSources()
        simSrcs = getAIPYSources()
            
        toUse = None
        print(name)
        for src in srcs.keys():
            if src.lower() == name.lower():
                toUse = src
                observer.date = datetime.utcfromtimestamp( t[t.size//2] )
                break
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
        junk1, az, junk2, junk3, el, junk4 = rpos.split(None, 5)
        az = ephem.degrees(az)
        el = ephem.degrees(el)
        
        bestT = 0.0
        bestV = 1e6
        for v in t:
            observer.date = datetime.utcfromtimestamp(v).strftime("%Y/%m/%d %H:%M:%S")
            srcs[toUse].compute(observer)
            
            sep = ephem.separation((srcs[toUse].az, srcs[toUse].alt), (az,el))
            if sep < bestV:
                bestT = v
                bestV = sep
        tTransit = bestT
        observer.date = datetime.utcfromtimestamp(tTransit).strftime("%Y/%m/%d %H:%M:%S")
        zenithAngle = ephem.degrees(ephem.degrees('90:00:00') - el)
        
        # Select data that was actually recorded
        good = numpy.where( (t > 0) & (I1[:,10] > 0) & (I2[:,10] > 0) )[0][:-1]
        t = t[good]
        I1 = I1[good,:]
        I2 = I2[good,:]
        
        # Sum over the inner 75% of the band
        toUseSpec = range(f1.size//8, 7*f1.size//8)
        I1 = I1[:,toUseSpec].sum(axis=1)
        I2 = I2[:,toUseSpec].sum(axis=1)
        
        # Convert the scales to unit flux
        I1 /= I1.max()
        I2 /= I2.max()
        
        # Find the center pointing
        raCnt, decCnt = {}, {}
        for s in stp:
            try:
                raCnt[s[1]] += 1
            except KeyError:
                raCnt[s[1]] = 1
            try:
                decCnt[s[2]] += 1
            except KeyError:
                decCnt[s[2]] = 1
        raCtr = max(raCnt.items(), key=operator.itemgetter(1))[0]
        decCtr = max(decCnt.items(), key=operator.itemgetter(1))[0]
        
        # Break the data into three pieces:
        #  onSrc - The on-source ionosphereic reference
        #  raCut - Points that are part of the RA cut (second half)
        #  decCut Points that are part of the Dec cut (first half)
        onSrc  = [i for i,s in enumerate(stp) if s[1] == raCtr and s[2] == decCtr and i%2 == 0]
        raCut  = [i for i,s in enumerate(stp) if (s[1] != raCtr and s[2] == decCtr) or \
                                        (s[1] == raCtr and s[2] == decCtr and i%2 == 1 and i > len(stp)//2 )]
        decCut = [i for i,s in enumerate(stp) if (s[1] == raCtr and s[2] != decCtr) or \
                                        (s[1] == raCtr and s[2] == decCtr and i%2 == 1 and i < len(stp)//2)] 
        
        # Pull out the mean data value for each step that has been observed
        m, ra, dec, pwr1, pwr2 = [], [], [], [], []
        for i in range(len(stp)):
            tStart = stp[i][0]
            try:
                tStop = stp[i+1][0]
            except IndexError:
                tStop = numpy.inf
                
            valid = numpy.where( (t>=tStart) & (t<tStop) )[0]
            m.append( t[valid].mean() )
            ra.append( stp[i][1] )
            dec.append( stp[i][2] )
            try:
                pwr1.append( robust.mean(I1[valid]) )
            except:
                pwr1.append( numpy.mean(I1[valid]) )
            try:
                pwr2.append( robust.mean(I2[valid]) )
            except:
                pwr2.append( numpy.mean(I2[valid]) )
        m, ra, dec, pwr1, pwr2 = numpy.array(m), numpy.array(ra), numpy.array(dec), numpy.array(pwr1), numpy.array(pwr2)
        
        # "Correct" for the ionosphere using the power as a function of time 
        # in the on-source reference
        fnc1 = interp1d(m[onSrc], pwr1[onSrc], kind='linear', bounds_error=False, fill_value=0.0)
        pwr1[ onSrc] /= fnc1(m[ onSrc])
        pwr1[ raCut] /= fnc1(m[ raCut])
        pwr1[decCut] /= fnc1(m[decCut])
        fnc2 = interp1d(m[onSrc], pwr2[onSrc], kind='linear', bounds_error=False, fill_value=0.0)
        pwr2[ onSrc] /= fnc2(m[ onSrc])
        pwr2[ raCut] /= fnc2(m[ raCut])
        pwr2[decCut] /= fnc2(m[decCut])
        
        # Weed out any bad points in the RA and dec cuts
        ## RA
        while True:
            for i,p in enumerate(raCut):
                if not numpy.isfinite(pwr1[p]) or not numpy.isfinite(pwr2[p]):
                    del raCut[i]
                    break
            break
        ## Dec
        while True:
            for i,p in enumerate(decCut):
                if not numpy.isfinite(pwr1[p]) or not numpy.isfinite(pwr2[p]):
                    del decCut[i]
                    break
            break
            
        # Plots and analysis
        fig = plt.figure()
        fig.suptitle('Source: %s @ %s\n%s' % (name, sta_name, rpos))
        ax11 = fig.add_subplot(2, 2, 1)
        ax12 = fig.add_subplot(2, 2, 2)
        ax21 = fig.add_subplot(2, 2, 3)
        ax22 = fig.add_subplot(2, 2, 4)
        for i,(ax1,ax2),f,pwr in zip((1,2), ((ax11,ax12), (ax21,ax22)), (f1.mean(), f2.mean()), (pwr1, pwr2)):
            if i == 2 and tuning1 is tuning2:
                continue
            print("Tuning %i @ %.3f MHz" % (i, f/1e6))
            
            ## Dec
            x = dec[decCut]
            xPrime = numpy.linspace(x.min(), x.max(), 101)
            y = pwr[decCut]
            p0 = (y.max()-y.min(), x.mean(), 2.0, y.min())
            p, status = leastsq(err, p0, args=(x, y))
            decOffset = ephem.degrees(str(p[1] - decCtr))
            fwhmD = ephem.degrees(str(p[2]))
            sefdMetricD = p[3] / p[0]
            print("  Dec")
            print("    FWHM Estimate: %s" % fwhmD)
            print("    Pointing Error: %s" % decOffset)
            if toUseAIPY is None:
                print("    1/(P1/P0 - 1): %.3f" % sefdMetricD)
                if name == srcs[toUse].name:
                        sefdEstimateD = numpy.nan
            else:
                try:
                    simSrcs[toUseAIPY].compute(observer, afreqs=f/1e9)
                    srcFlux = simSrcs[toUseAIPY].jys
                except TypeError:
                    f0, index, Flux0 = simSrcs[toUseAIPY].mfreq, simSrcs[toUseAIPY].index, simSrcs[toUseAIPY]._jys
                    srcFlux = Flux0 * (f/1e9 / f0)**index
                sefd = srcFlux*sefdMetricD / 1e3
                print("    S / (P1/P0 - 1): %.3f kJy" % sefd)
                if name == srcs[toUse].name:
                        sefdEstimateD = sefd*1e3
                        
            ax = ax1
            ax.plot(x, y, linestyle='', marker='+', label='Data')
            ax.plot(xPrime, func(p, xPrime), linestyle='-', label='Fit')
            ax.vlines(decCtr, *ax.get_ylim(), linestyle=':')
            ax.legend(loc=0)
            ax.set_xlabel('Dec. [$^\\circ$]')
            ax.set_ylabel('Power [arb., corr.]')
            
            ## RA
            x = ra[raCut]
            xPrime = numpy.linspace(x.min(), x.max(), 101)
            y = pwr[raCut]
            p0 = (y.max()-y.min(), x.mean(), 2.0/15.0, y.min())
            p, status = leastsq(err, p0, args=(x, y))
            raOffset = ephem.hours(str(p[1] - raCtr))
            fwhmR = ephem.degrees(str(p[2]*15 * numpy.cos(decCtr*numpy.pi/180.0)))
            sefdMetricR = p[3] / p[0]
            print("  RA")
            print("    FWHM Estimate: %s" % fwhmR)
            print("    Pointing Error: %s" % raOffset)
            if toUseAIPY is None:
                print("    1/(P1/P0 - 1): %.3f" % sefdMetricR)
                if name == srcs[toUse].name:
                        sefdEstimateR = numpy.nan
            else:
                try:
                    simSrcs[toUseAIPY].compute(observer, afreqs=f/1e9)
                    srcFlux = simSrcs[toUseAIPY].jys
                except TypeError:
                    f0, index, Flux0 = simSrcs[toUseAIPY].mfreq, simSrcs[toUseAIPY].index, simSrcs[toUseAIPY]._jys
                    srcFlux = Flux0 * (f/1e9 / f0)**index
                sefd = srcFlux*sefdMetricR / 1e3
                print("    S / (P1/P0 - 1): %.3f kJy" % sefd)
                if name == srcs[toUse].name:
                        sefdEstimateR = sefd*1e3
            
            ax = ax2
            ax.plot(x, y, linestyle='', marker='+', label='Data')
            ax.plot(xPrime, func(p, xPrime), linestyle='-', label='Fit')
            ax.vlines(raCtr, *ax.get_ylim(), linestyle=':')
            ax.legend(loc=0)
            ax.set_xlabel('RA [$^h$]')
            ax.set_ylabel('Power [arb., corr.]')
            
            # Save
            fwhmEstimate = ephem.degrees((fwhmD + fwhmR) / 2.0)
            sefdEstimate = (sefdEstimateD + sefdEstimateR) / 2.0
            finalResults.append( "%-6s %-19s %6.3f %-10s %-10s %-10s %10.3f %-10s" % \
                                (srcs[toUse].name, datetime.utcfromtimestamp(tTransit).strftime("%Y/%m/%d %H:%M:%S"), f/1e6, zenithAngle, raOffset, decOffset, sefdEstimate, fwhmEstimate) )
            
        if args.headless:
            figname = os.path.basename(filename)
            figname = os.path.splitext(figname)[0]
            fig.savefig(figname+'.png')
        else:
            plt.show()
            
    # Final report
    sys.stderr.write("Source YYYY/MM/DD HH:MM:SS MHz    Z          errRA      errDec      SEFD      FWHM\n")
    for line in finalResults:
        print(line)


if __name__ == "__main__":
    numpy.seterr(all='ignore')
    parser = argparse.ArgumentParser(
        description='given a HDF5 file associated with an observation generated by generateWeave.py, determine the current pointing offset and estimate the FWHM',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument('filename', type=str, nargs='+', 
                        help='HDF5 file to analyze')
    sgroup = parser.add_mutually_exclusive_group(required=False)
    sgroup.add_argument('-v', '--lwasv', action='store_true',
                        help='use LWA-SV instead of LWA1 if the station is not specified in the HDF5 file')
    sgroup.add_argument('-o', '--ovrolwa', action='store_true',
                        help='use OVRO-LWA instead of LWA1 if the station is not specified in the HDF5 file')
    parser.add_argument('--headless', action='store_true',
                        help='run in headless mode and save figures to disk')
    args = parser.parse_args()
    if args.headless:
        import matplotlib
        matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    
    main(args)
    
