#!/usr/bin/env python3

"""
Script to run a stress test during an idle window that corresponds to CygA
transit.
"""

import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta
from socket import gethostname

from lwa_mcs.tp import schedule_sdfs
from lwa_mcs.utils import schedule_at_command
from lwa_mcs.exc import cancel_observation


# Obsever and project information
_OBSERVER_NAME = 'Jayce Dowell`'
_OBSERVER_ID = 99
_PROJECT_NAME = 'CygA Stress Test'
_PROJECT_ID = 'COMST'


# Station information
_IS_LWASV = gethostname().lower().find('lwasv') != -1


def main(args):
    # Get the start and stop times for the window that we are scheduling
    start = datetime.strptime('%s %s' % (args.start_date, args.start_time), '%Y/%m/%d %H:%M:%S')
    stop  = datetime.strptime('%s %s' % (args.stop_date, args.stop_time), '%Y/%m/%d %H:%M:%S')
    print("Scheduling stress test for %s to %s" % (start.strftime('%Y/%m/%d %H:%M:%S'),  
                                                   stop.strftime('%Y/%m/%d %H:%M:%S')))
    print("  Window is %.1f min long" % ((stop-start).total_seconds()/60.0,))
    
    mid = start + (stop-start)/2
    print("  Mid-point is %s" % (mid.strftime('%Y/%m/%d %H:%M:%S'),))
    
    # Load in the next session ID
    try:
        fh = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state'), 'r')
        line = fh.read()
        old_project_id, session_id = line.split(None, 1)
        session_id = int(session_id, 10)
        fh.close()
        ## Check so that we can reset the session ID whenever the project code changes
        if old_project_id != _PROJECT_ID:
            raise ValueError
    except (IOError, ValueError):
        session_id = 1
        
    # Make sure we have a place to put the SDFs
    sdf_dir = "/home/op1/MCS/tp/%s/" % start.strftime("%y%m%d")
    if not args.dry_run:
        if not os.path.exists(sdf_dir):
            print("Creating date directory: %s" % sdf_dir)
            os.mkdir(sdf_dir)
            
    # Generate the run and get the filename
    cmd = ['./generateWeave.py', '-s', str(session_id), '-u', 'stress_tests']
    if _IS_LWASV:
        cmd.append('-v')
    cmd.extend(['CygA', mid.strftime("%Y/%m/%d"), mid.strftime("%H:%M:%S")])
    output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                     cwd=os.path.abspath(os.path.dirname(__file__)))
    output = output.decode()
    output = output.split('\n')
    filename = output[-2].split(None, 1)[1]
    filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), filename)
    newname = os.path.join(sdf_dir, filename)
    
    # Move it into place
    if not args.dry_run:
        os.rename(filename, newname)
    else:
        #os.unlink(filename)
        pass
    filenames = [newname,]
    session_id += 1
    
    # Submit the SDFs
    print("Submitting SDFs for scheduling")
    if not args.dry_run and filenames:
        bi = busy.BusyIndicator(message="'waiting'")
        bi.start()
        try:
            success = schedule_sdfs(filenames, max_retries=10)
        except Exception as scheduling_error:
            success = False
            print("schedule_sdfs() failed with '%s'" % str(scheduling_error))
        bi.stop()
        if not success:
            fh = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runtime.log'), 'a')
            fh.write("Failed Scheduling for UTC %s to %s\n" % (start.strftime('%Y/%m/%d %H:%M:%S'), 
                                                               stop.strftime('%Y/%m/%d %H:%M:%S')))
            fh.write("  Scheduling Error:\n")
            try:
                fh.write("    %s\n" % scheduling_error)
            except NameError:
                fh.write("    Too many failed attempts to schedule\n")
            fh.close()
            
            for fileid in fileids:
                try:
                    cancel_observation(_PROJECT_ID, fileid, remove_metadata=True)
                    print("  Removed session %i" % fileid)
                except RuntimeError:
                    pass
                    
            print("There seems to be an issue with scheduling the SDFs, giving up!")
            print("Script is aborted!")
            sys.exit(1)
            
    print("SDFs successfully scheduled")
    if not args.dry_run:
        # Write out new session id
        fh = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state'), 'w')
        fh.write("%s %i\n" % (_PROJECT_ID, session_id))
        fh.close()
        
    print("Done, saving log")
    if not args.dry_run:
        fh = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runtime.log'), 'a')
        fh.write("Completed Scheduling for UTC %s to %s\n" % (start.strftime('%Y/%m/%d %H:%M:%S'), 
                                                              stop.strftime('%Y/%m/%d %H:%M:%S')))
        fh.write("  Command:\n")
        fh.write("    %s\n" % (' '.join(cmd),))
        fh.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Schedule a CygA stress test')
    parser.add_argument('start_date', type=str, 
                        help='scheduling window UTC start date in YYYY/MM/DD format')
    parser.add_argument('start_time', type=str,
                        help='scheduling window UTC start time in HH:MM:SS format')
    parser.add_argument('stop_date', type=str, 
                        help='scheduling window UTC stop date in YYYY/MM/DD format')
    parser.add_argument('stop_time', type=str,
                        help='scheduling window UTC stop time in HH:MM:SS format')
    parser.add_argument('-n', '--dry-run', action='store_true', 
                        help='perform a dry-run only')
    args = parser.parse_args()
    main(args)
