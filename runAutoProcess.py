#!/usr/bin/env python3

import os
import sys
import glob
import stat
import shutil
import getpass
import subprocess
from socket import gethostname

from lsl.common import metabundle, metabundleADP
try:
    from lsl.common import metabundleNDP
except ImportError:
    # Catch for older LSL
    metabundleNDP = metabundleADP
    
from lsl.common._metabundle_utils import *


def get_mcs_hostname(tarname):
    """
    Given an MCS meta-data tarball, extract the information stored in the mcs.host 
    file and return it as a string.
    
    If a mcs.host file cannot be found in the tarball, 'unknown' is returned.  
    """
    
    with managed_mkdtemp(prefix='metadata-bundle-') as tempDir:
        # Extract the SSMIF and SDM files.  If the ssmif.dat file cannot be found, None
        # is returned via the try...except block
        tf = _open_tarball(tarname)
        try:
            ti = tf.getmember('mcs.host')
        except KeyError:
            return 'unknown'
        tf.extractall(path=tempDir, members=[ti,])
        
        # Read in the name
        with open(os.path.join(tempDir, 'mcs.host'), 'r') as fh:
            name = fh.read().strip()
            
    # Return
    return name


# Where to find data to analyze
SEARCH_DIR = '/data/network/recent_data/stress_tests/'

# Where we come from
SELF_DIR = os.path.abspath(os.path.dirname(__file__))

# Where to find the DRX/HDF5 commissioning tools we need
COM_HDF5_DIR = '/usr/local/extensions/Commissioning/DRX/HDF5/'


def main(args):
    # Find the two most recent metadata files
    metadata = glob.glob(os.path.join(SEARCH_DIR, '*.tgz'))
    metadata.sort(key=lambda x: os.path.getmtime(x))
    metadata = metadata[-3:]
    
    for meta in metadata:
        ## Load in the metadata
        is_lwana = False
        is_lwasv = False
        sstyle = metabundle.get_style(meta)
        if sstyle.endswith('metabundleDP'):
            smd = metabundle.get_session_metadata(meta)
            sname = 'LWA1'
            oname = 'lwa1'
        elif sstyle.endswith('metabundleADP'):
            smd = metabundleADP.get_session_metadata(meta)
            is_lwasv = True
            sname = 'LWA-SV'
            oname = 'lwasv'
        elif sstyle.endswith('metabundleNDP'):
            smd = metabundleNDP.get_session_metadata(meta)
            is_lwana = True
            sname = 'LWA-NA'
            oname = 'lwana'
            
            oname = get_mcs_hostname(meta)
            if oname.startswith('lwa1'):
                is_lwana = False
                sname = 'LWA1'
                oname = 'lwa1'
                
        else:
            print(f"Unknown metadata style '{sstyle}' for {os.path.basename(meta)}, skipping")
            continue
        print(f"Working on {os.path.basename(meta)} from {sname}")
        
        ## Make sure the data are ready
        data = os.path.join(SEARCH_DIR, smd[1]['tag'])
        if not os.path.exists(data):
            print(f"WARNING: No data file found for {os.path.basename(meta)}, skipping")
            continue
        if not bool(os.stat(data).st_mode & stat.S_IROTH):
            print(f"WARNING: Data file not finished copying for {os.path.basename(meta)}, skipping")
            continue
        if os.path.getsize(data) == 0:
            print(f"WARNING: Data file for {os.path.basename(meta)} appears to be empty, skipping")
            continue
            
        ## Convert
        cmd = [sys.executable, os.path.join(COM_HDF5_DIR, 'drspec2hdf.py'), '-m', meta, data]
        try:
            subprocess.check_call(cmd, cwd=SEARCH_DIR)
        except subprocess.CalledProcessError as e:
            print(f"WARNING:  Failed to build HDF5 file for {os.path.basename(meta)} - {e}")
            continue
            
        ## Analyze and report
        cmd = [sys.executable, os.path.join(SELF_DIR, 'processWeave.py'), '--headless', data+'-waterfall.hdf5']
        try:
            output = subprocess.check_output(cmd, cwd=SELF_DIR)
        except subprocess.CalledProcessError as e:
            print(f"WARNING:  Failed to analyze HDF5 file {os.path.basename(meta)} - {e}")
            continue
        output = output.decode()
        lines = output.split('\n')
        for line in lines:
            print(f"  {line}")
            
        ## Record
        outname = os.path.join(SELF_DIR, 'metric-')
        outname += oname
        with open(outname, 'a') as fh:
            fh.write(output)
        figname = os.path.basename(data)
        figname = os.path.splitext(figname)[0]
        figname += '-waterfall.png'
        newname = os.path.join(SEARCH_DIR, figname)
        figname = os.path.join(SELF_DIR, figname)
        try:
            shutil.move(figname, newname)
        except OSError:
            print(f"WARNING: Failed to move output image {os.path.basename(figname)}")
            
        ## Upload to the OpScreen page
        for script in ('uploadSEFD.py', 'influxSEFD.py', 'influxSEFD_SV.py', 'influxSEFD_NA.py'):
            cmd = [sys.executable, os.path.join(SELF_DIR, script),]
            if not os.path.exists(cmd[0]):
                continue
                
            try:
                subprocess.check_call(cmd, cwd=SELF_DIR)
            except subprocess.CalledProcessError as e:
                print(f"WARNING: failed to upload results to the OpScreen page with {script} - {e}")
                
        ## Cleanup
        for filename in (meta, data):
            try:
                os.unlink(filename)
            except OSError:
                print(f"WARNING: Failed to remove {os.path.basename(filename)}")


if __name__ == '__main__':
    if not gethostname().startswith('lwaucf'):
        raise RuntimeError("Must by run on the LWAUCF")
    if getpass.getuser() != 'mcsdr':
        raise RuntimeError("Must be run by mcsdr")
        
    main(sys.argv[1:]) 
