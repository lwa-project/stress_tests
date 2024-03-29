Pointing and Sensitivity Check Utilities
========================================
This directory contains a set of utilities for running pointing and 
sensitivity checks at LWA1 and LWA-SV.

observationTimes.py
-------------------
Given a source name and a UTC date, generate a list of times the source
is at transit and elevations of 30, 40, 50, 60, 70, 80, and 90 degrees 
(when applicable).

generateDrifts.py
-----------------
Given a source name and a time from observationTimes.py, generate a 
collection of SDFs to carry out the run using the DR spectrometer mode.
The spectrometer mode is set up to deliver 1,024 channels and 6,144 
windows per integration.  This translates to a spectral resolution of 
19.1 kHz and a temporal resolution of 0.321 seconds.

generateWeave.py
----------------
Similar to generateDrifts.py but only uses a single beam to do a set
of RA and dec. cuts across the specified source.  The spectrometer 
mode is set up to deliver 1,024 channels and 768 windows per 
integration.  This translates to a spectral resolution of 19.1 kHz and
a temporal resolution of 0.040 seconds.

processDrifts.py
----------------
Given the HDF5 versions of data collected from the generateDrifts.py 
SDFs, fit the pointing error and estimate the SEFD and FWHM.

processWeave.py
---------------
Similar to processDrifts.py but for the HDF5 output of data collected
through generateWeave.py.

fitPointingError.py
-------------------
Given a file containing the results of several processDrifts.py runs,
fit the pointing error as a rotation-about-an-axis.  Return the best-
fit axisand generate a plot showing the change in pointing error.

plotSkyCoverage.py
------------------
Given a file containing the results of several processDrifts.py runs,
plot the sky coverage of the observations to determine if the sky is 
well sampled.

plotSEFDEstimates.py
--------------------
Given a file containing the results of several processDrifts.py runs, 
plot the SEFD estimates as a function of zenith angle.

plotFWHMEstimates.py
--------------------
Given a file containing the results of several processDrifts.py runs, 
plot the FWHM estimates as a function of zenith angle.

makeTable.py
------------
Given a file containing the results of several processDrifts.py runs, 
create a LaTeX table of the sources observed that is suitable for 
inclusion in the "LWA1 Pointing Error and Correction" memo.
