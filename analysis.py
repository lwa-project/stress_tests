
"""
Module to parse the results file for a collection of pointing checks.
"""

from __future__ import print_function, division

import aipy
import ephem
import numpy
from datetime import datetime
from multiprocessing import Pool
from scipy.optimize import leastsq

from lsl.common import stations
from lsl.sim.vis import SOURCES as simSrcs
from lsl.common.mcs import apply_pointing_correction

__version__ = "0.2"
__all__ = ['getSources', 'getAIPYSources', 'parse', 'fitDataWithRotation', 
           '__version__', '__all__']


# List of bright radio sources and pulsars in PyEphem format
_srcs = ["TauA,f|J,05:34:32.00,+22:00:52.0,1", 
         "VirA,f|J,12:30:49.40,+12:23:28.0,1",
         "CygA,f|J,19:59:28.30,+40:44:02.0,1", 
         "CasA,f|J,23:23:27.94,+58:48:42.4,1",
         "3C123,f|J,04:37:04.38,+29:40:13.8,1",
         "3C295,f|J,14:11:20.47,+52:12:09.5,1",
         "HerA,f|J,16:51:08.15,+04:59:33.3,1",
         "SgrA,f|J,17:45:40.00,-29:00:28.0,1",
         "HydA,f|J,09:18:05.65,-12:05:44.0,1"]


class RadioBodyBaars:
    """
    Class defining flux of a celestial source using the Baars a, b, and c parameters.

    Based on the aipy.amp.RadioBody class
    """
    def __init__(self, a, b, c, secularChange=0.0, secularEpoch=2013.0):
        """
        Flux parameters where:
        log S = a + b*log(nu/1MHz) + c*log(nu/1MHz)**2
        with the posibility of a secular evolution since a certain
        epoch (as a year).
        """
        
        self.a = a
        self.b = b
        self.c = c
        self.secularChange = secularChange
        self.secularEpoch = secularEpoch
        self.mfreq = 1e6 / 1e9	# 1 MHz
        
    def update_jys(self, afreqs, epoch=2013.0):
        """
        Update fluxes relative to the provided observer.  Must be called at 
        each time step before accessing information.
        """

        flux = 10**(self.a + self.b*numpy.log10(afreqs/self.mfreq) + self.c*numpy.log10(afreqs/self.mfreq)**2)
        flux *= (1 + self.secularChange)**(epoch-self.secularEpoch)
        
        self.jys = flux
        
    def get_jys(self):
        """
        Return the fluxes vs. freq that should be used for simulation.
        """
        
        return self.jys


class RadioFixedBodyBaars(aipy.phs.RadioFixedBody, RadioBodyBaars):
    """
    Class representing a source at fixed RA,DEC.  Adds Baars-style flux 
    information to aipy.phs.RadioFixedBody.

    Based on the aipy.amp.RadioFixedBody class
    """
    
    def __init__(self, ra, dec, name='', epoch=ephem.J2000, a=1.0, b=0.0, c=0.0, secularChange=0.0, secularEpoch=2013.0, mfreq=0.001, ionref=(0.,0.), srcshape=(0.,0.,0.), **kwargs):
        """
        ra = source's right ascension (epoch=J2000)
        dec = source's declination (epoch=J2000)
        jys = source strength in Janskies at mfreq)
        mfreq = frequency (in GHz) where source strength was measured
        index = power-law index of source emission vs. freq.
        """
        
        aipy.phs.RadioFixedBody.__init__(self, ra, dec, mfreq=mfreq, name=name, epoch=epoch, ionref=ionref, srcshape=srcshape)
        RadioBodyBaars.__init__(self, a, b, c, secularChange=secularChange, secularEpoch=secularEpoch)
        
    def compute(self, observer, afreqs=74e-3):
        epoch = datetime.strptime(str(observer.date), "%Y/%m/%d %H:%M:%S")
        epoch = epoch.year + float(epoch.strftime("%j")) / 365

        aipy.phs.RadioFixedBody.compute(self, observer)
        try:
            self.update_jys(observer.get_afreqs(), epoch=epoch)
        except AttributeError:
            self.update_jys(afreqs, epoch=epoch)


def getSources():
    """
    Return a dictionary of PyEphem sources.
    """
    
    srcs = {}
    for line in _srcs:
        src = ephem.readdb(line)
        srcs[src.name] = src
        
    return srcs


def getAIPYSources():
    """
    Return a dictionary of AIPY sources.
    
    .. note::
        This function returns a slightly different dictionary that than 
        contained in lsl.sim.vis.srcs.  First, this dictionary has source 
        names that are consistent with those returned by the getSources()
        function.  Second, this list contains 3C123.
    """
    
    newSrcs = {}
    for name,src in simSrcs.items():
        if name == 'Sun':
            newSrcs[name] = src
        elif name == 'Jupiter':
            newSrcs[name] = src
        elif name == 'crab':
            newSrcs['TauA'] = src
        else:
            newSrcs['%sA' % name.capitalize()] = src
    newSrcs['3C123'] = aipy.amp.RadioFixedBody('4:37:04.38', '+29:40:13.8', jys=206.0, index=-0.70, mfreq=0.178)
    newSrcs['HydA']  = aipy.amp.RadioFixedBody('9:18:05.65', '-12:05:44.0', jys=1860., index=-2.30, mfreq=0.160)
    
    # Modify CygA, TauA, VirA, and CasA for the Baars et al. (1977) fluxes.  
    # For CasA, include the Helmboldt & Kassim secular decrease of 0.84%/yr
        # -> (Helmboldt & Kassim 2009, AJ, 138, 838)
    newSrcs['CygA'] = RadioFixedBodyBaars('19:59:28.30', '+40:44:02.0', a=4.695, b=0.085, c=-0.178)
    newSrcs['TauA'] = RadioFixedBodyBaars('05:34:32.00', '+22:00:52.0', a=3.915, b=-0.299)
    newSrcs['VirA'] = RadioFixedBodyBaars('12:30:49.40', '+12:23:28.0', a=5.023, b=-0.856)
    newSrcs['CasA'] = RadioFixedBodyBaars('23:23:27.94', '+58:48:42.4', a=5.625, b=-0.634, c=-0.023,
                        secularChange=-0.0084, secularEpoch=1965.0)
    newSrcs['3C295'] = RadioFixedBodyBaars('14:11:20.47', '+52:12:09.5', a=1.485, b=0.759, c=-0.255)
    
    return newSrcs


def parse(filename, station=stations.lwa1):
    # Get a list of sources to compare with
    srcs = getSources()
    
    # Get an observer for the station
    obs = station.get_observer()
    
    # Open the file and run with it
    fh = open(filename, 'r')
    
    data = []
    for line in fh:
        line = line.replace('\n', '')
        
        # Skip over comments and blank lines
        if len(line) < 3:
            continue
        elif line[0] == '#':
            continue
        elif line[:6] == 'Source':
            continue
            
        # Split
        fields = line.split()
        nFields = len(fields)
        if nFields == 9:
            srcName, dateStr, timeStr, freq_MHz, zenithAngle, raError, decError, sefd, fwhm = fields
        elif nFields == 8:
            srcName, dateStr, timeStr, zenithAngle, raError, decError, sefd, fwhm = fields
            freq_MHz = '-1.0'
        elif nFields == 7:
            srcName, dateStr, timeStr, zenithAngle, raError, decError, sefd = fields
            freq_MHz = '-1.0'
            fwhm = '-1.0'
        else:
            raise RuntimeError("Expected 7, 8, or 9 fields per line, found %i" % nFields)
            
        # Convert the date to a '/'d format
        try:
            dateStr = dateStr.replace('-', '/')
            timeStr, junk = timeStr.split('.', 1)
        except ValueError:
            pass
            
        ## Basic parameters
        entry = {}
        entry['name'] = srcName
        entry['date'] = '%s %s' % (dateStr, timeStr)
        entry['freq_MHz'] = float(freq_MHz)
        entry['raError'] = ephem.hours(raError)
        entry['decError'] = ephem.degrees(decError)
        entry['SEFD'] = float(sefd)
        entry['FWHM'] = ephem.degrees(fwhm)
        entry['zenithAngle'] = ephem.degrees(zenithAngle)
        
        ## Compute the true az/el of the source
        obs.date = entry['date']
        srcs[srcName].compute(obs)
        entry['az'] = srcs[srcName].az
        entry['el'] = srcs[srcName].alt
        
        ## Compute the az/el for the "expected" source location
        correctedSrc = ephem.FixedBody()
        correctedSrc._ra  = srcs[srcName]._ra  + entry['raError']
        correctedSrc._dec = srcs[srcName]._dec + entry['decError']
        correctedSrc.compute(obs)
        entry['correctedAz'] = correctedSrc.az
        entry['correctedEl'] = correctedSrc.alt
        
        data.append( entry )
    fh.close()
    
    return data


def _driftscanFunction(p, x):
    height = p[0]
    center = p[1]
    width  = p[2]
    offset = p[3]
    try:
        slope  = p[4]
    except IndexError:
        slope = 0.0
    
    y = height*numpy.exp(-4*numpy.log(2)*(x - center)**2/width**2 ) + slope*x + offset
    return y


def _driftscanErrorFunction(p, x, y):
    yFit = _driftscanFunction(p, x)
    return y - yFit 


def fitDriftscan(t, power, includeLinear=False):
    """
    Given an array of times and and array of total power from a drift scan, 
    fit the drift scan with a Gaussian to estimate the RA error, SEFD, and
    FWHM.  Return the results as a four-element tuple of:
    1) time of peak, 
    2) SEFD metric (1/(P1/P0 - 1), 
    3) FWHM in seconds
    4) best-fit values
    """
    
    gp = [power.max()-power.min(), t.mean(), 1000, power.min()]
    if includeLinear:
        gp.append(0.0)
    gp, status = leastsq(_driftscanErrorFunction, gp, (t, power))
    
    tPeak = gp[1]
    sefdMetric = gp[3]/gp[0]
    fwhm = abs(gp[2])
    
    fit = _driftscanFunction(gp, t)
    
    if includeLinear:
        slope = gp[4]
        return tPeak, sefdMetric, fwhm, slope, fit
    else:
        return tPeak, sefdMetric, fwhm, fit


def _decFunction(p, x, fwhm):
    height = p[0]
    center = p[1]
    offset = p[2]
    width = fwhm
    
    y = height*numpy.exp(-4*numpy.log(2)*(x - center)**2/width**2 ) + offset
    return y


def _decErrorFunction(p, x, y, fwhm):
    yFit = _decFunction(p, x, fwhm)
    return y - yFit 


def fitDecOffset(decs, powers, fwhm=2.0):
    """
    Given an array of declination offsets from the source and the peak 
    power seen from each driftscan, estimate the declination pointing 
    error.
    
    .. note::
        To reduce the number of samples needed for the fit, the FWHM is
        specified during the fitting.  The default value used is two 
        degrees.
    """
    
    gp = [powers.max()-powers.min(), 0.0, powers.min()]
    gp, status = leastsq(_decErrorFunction, gp, (decs, powers, fwhm))
    
    return gp[1]


def _rotationErrorFunction(data, theta, phi, psi, verbose=False):
    error = 0.0
    count = 0
    
    for entry in data:
        srcName = entry['name']
        az = float(entry['az']) * 180.0/numpy.pi
        el = float(entry['el']) * 180.0/numpy.pi
        
        azP, elP = apply_pointing_correction(az, el, theta, phi, psi, degrees=True)
        azP = ephem.degrees(azP * numpy.pi/180.0)
        elP = ephem.degrees(elP * numpy.pi/180.0)
        
        sep = ephem.separation((entry['correctedAz'],entry['correctedEl']), (azP,elP))
        if verbose:
            print("%s with a separation of %s" % (srcName, sep))
            
        error += sep**2
        count += 1
        
    return numpy.sqrt(error / float(count))


def _rotationErrorFunctionPool(data, theta, phi, psis):
    rmss = []
    
    for psi in psis:
        error = 0.0
        count = 0
        
        for i in range(data.shape[0]):
            az = data[i,0]
            el = data[i,1]
            correctedAz = ephem.degrees(data[i,2] * numpy.pi/180.0)
            correctedEl = ephem.degrees(data[i,3] * numpy.pi/180.0)
            
            azP, elP = apply_pointing_correction(az, el, theta, phi, psi, degrees=True)
            azP = ephem.degrees(azP * numpy.pi/180.0)
            elP = ephem.degrees(elP * numpy.pi/180.0)
            
            sep = ephem.separation((correctedAz,correctedEl), (azP,elP))
            
            error += sep**2
            count += 1
            
        rmss.append( numpy.sqrt(error / float(count)) )
        
    return numpy.array(rmss)


def fitDataWithRotation(data, thetas, phis, psis, usePool=False):
    """
    Given a list of observer pointing errors, and lists of theta, phi
    and psi values, fit the data with a rotation-abount-an-axis and return
    a four-element tuple of theta, phi, psi, and pointing RMS.
    """
    
    if usePool:
        taskPool = Pool()
        taskList = []
        
        dataCollapsed = numpy.zeros((len(data),4))
        for i,entry in enumerate(data):
            dataCollapsed[i,0] = float(entry['az']) * 180.0/numpy.pi
            dataCollapsed[i,1] = float(entry['el']) * 180.0/numpy.pi
            dataCollapsed[i,2] = float(entry['correctedAz']) * 180.0/numpy.pi
            dataCollapsed[i,3] = float(entry['correctedEl']) * 180.0/numpy.pi
            
        for theta in thetas:
            for phi in phis:
                task = taskPool.apply_async(_rotationErrorFunctionPool, args=(dataCollapsed, theta, phi, psis))
                taskList.append( (theta,phi,task) )
        taskPool.close()
        taskPool.join()
        
        bestValue = 1e6
        best = None
        for theta,phi,task in taskList:
            rmss = task.get()
            
            if rmss.min() < bestValue:
                b = numpy.where( rmss == rmss.min() )[0][0]
                psi = psis[b]
                
                best = (theta,phi,psi)
                bestValue = rmss.min()
                
    else:
        bestValue = 1e6
        best = None
        for theta in thetas:
            for phi in phis:
                for psi in psis:
                    rms = _rotationErrorFunction(data, theta, phi, psi)
                    
                    if rms < bestValue:
                        best = (theta, phi, psi)
                        bestValue = rms
                        
    return best[0], best[1], best[2], bestValue * 180.0/numpy.pi
