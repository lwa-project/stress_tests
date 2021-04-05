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
    metadata = metadata[-2:]
    
    for meta in metadata:
        ## Load in the metadata
        if metabundleADP.is_valid(meta):
            smd = metabundleADP.get_session_metadata(meta)
            is_lwasv = True
        else:
            smd = metabundle.get_session_metadata(meta)
            is_lwasv = False
        print(f"Working on {os.path.basename(meta)} from {'LWA-SV' if is_lwasv else 'LWA1'}")
        
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
        cmd = [os.path.join(COM_HDF5_DIR, 'drspec2hdf.py'), '-m', meta, data]
        try:
            subprocess.check_call(cmd, cwd=SEARCH_DIR)
        except subprocess.CalledProcessError as e:
            print(f"WARNING:  Failed to build HDF5 file for {os.path.basename(meta)} - {e}")
            continue
            
        ## Analyze and report
        cmd = [os.path.join(SELF_DIR, 'processWeave.py'), '--headless', data+'-waterfall.hdf5']
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
        outname += ('lwasv' if is_lwasv else 'lwa1')
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
        cmd = [os.path.join(SELF_DIR, 'uploadSEFD.py'),]
        try:
            subprocess.check_call(cmd, cwd=SELF_DIR)
        except subprocess.CalledProcessError:
            print("WARNING: failed to upload results to the OpScreen page")
            
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
