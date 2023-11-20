#!/usr/bin/env python3

"""
Script to run a stress test during an idle window that corresponds to CygA
transit.
"""

import os
import sys
import math
import argparse
import subprocess
from datetime import datetime, timedelta
from socket import gethostname

from lsl.common import stations, sdf, sdfADP, sdfNDP, busy
from lsl.common.mcs import mjdmpm_to_datetime

from lwa_mcs.tp import schedule_sdfs
from lwa_mcs.utils import schedule_at_command
from lwa_mcs.exc import cancel_observation

from analysis import getSources


# Obsever and project information
_OBSERVER_NAME = 'Jayce Dowell`'
_OBSERVER_ID = 99
_PROJECT_NAME = 'CygA Stress Test'
_PROJECT_ID = 'COMST'


# Station information
_IS_LWASV = gethostname().lower().find('lwasv') != -1
_IS_LWANA = gethostname().lower().find('lwana') != -1


def main(args):
    # Get the start and stop times for the window that we are scheduling
    start = datetime.strptime('%s %s' % (args.start_date, args.start_time), '%Y/%m/%d %H:%M:%S')
    stop  = datetime.strptime('%s %s' % (args.stop_date, args.stop_time), '%Y/%m/%d %H:%M:%S')
    print("Scheduling stress test for %s to %s" % (start.strftime('%Y/%m/%d %H:%M:%S'),  
                                                   stop.strftime('%Y/%m/%d %H:%M:%S')))
    print("  Window is %.1f min long" % ((stop-start).total_seconds()/60.0,))
    
    # Find the mid-point
    mid = start + (stop-start)/2
    print("  Mid-point is %s" % (mid.strftime('%Y/%m/%d %H:%M:%S'),))
    
    # Tweak the mid-point to get closer to transit
    cyga = getSources()['CygA']
    site = stations.lwa1
    if _IS_LWASV:
        site = stations.lwasv
    elif _IS_LWANA:
        site = stations.lwana
    site.date = mid.strftime('%Y/%m/%d %H:%M:%S')
    cyga.compute(site)
    diff = cyga.ra - site.sidereal_time()
    mid += timedelta(seconds=int(round(diff*12*3600 / math.pi)))
    print("  Transit is %s" % (mid.strftime('%Y/%m/%d %H:%M:%S'),))
    
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
    cmd = [sys.executable, './generateWeave.py', '-s', str(session_id), '-u', 'stress_tests']
    if _IS_LWASV:
        cmd.append('-v')
    elif _IS_LWANA:
        cmd.append('-n')
    cmd.extend(['CygA', mid.strftime("%Y/%m/%d"), mid.strftime("%H:%M:%S")])
    output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                     cwd=os.path.abspath(os.path.dirname(__file__)))
    output = output.decode()
    output = output.split('\n')
    filename = output[-2].split(None, 1)[1]
    newname = os.path.join(sdf_dir, filename)
    filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), filename)
    
    # Parse it to get an "official" start/stop time
    parser = sdf
    if _IS_LWASV:
        parser = sdfADP
    elif _IS_LWANA:
        parser = sdfNDP
    test_plan = parser.parse_sdf(filename)
    test_beam = test_plan.sessions[0].drx_beam
    test_start = mjdmpm_to_datetime(test_plan.sessions[0].observations[0].mjd,
                                    test_plan.sessions[0].observations[0].mpm)
    test_stop = mjdmpm_to_datetime(test_plan.sessions[0].observations[-1].mjd,
                                   test_plan.sessions[0].observations[-1].mpm \
                                   + test_plan.sessions[0].observations[-1].dur)
    
    # Move it into place
    if not args.dry_run:
        os.rename(filename, newname)
    else:
        os.unlink(filename)
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
        
    print("Scheduling 'at' commands")
    atCommands = []
    atIDs = []
    if _IS_LWASV or _IS_LWANA:
        tDRX = stop - timedelta(minutes=1)
        tDRX = tDRX.replace(second=0, microsecond=0)
        atCommands.append( (tDRX, '/home/op1/MCS/exec/set_default_freqs.sh') )
        
    else:
        tINI = start + timedelta(minutes=2)
        tINI = tINI.replace(second=0, microsecond=0)
        atCommands.append( (tINI, '/home/op1/MCS/sch/INIdp.sh') )
        
        tTBN = stop - timedelta(minutes=1)
        tTBN = tTBN.replace(second=0, microsecond=0)
        atCommands.append( (tTBN, '/home/op1/MCS/sch/startTBN_split.sh') )
        
    ## Implement the commands
    for atcmd in atCommands:
        if not args.dry_run:
            atID = schedule_at_command(*atcmd)
        else:
            atID = -1
        atIDs.append(atID)
        
    print("Done, saving log")
    if not args.dry_run:
        rpt = []
        for atcmd,id in zip(atCommands,atIDs):
            if id != -1:
                id = " (#%i)" % id
            else:
                id = ''
            rpt.append( [atcmd[0], "%s%s" % (atcmd[1], id)] )
        rpt.append( [test_start, f"stress tests starts on beam {test_beam}"] )
        rpt.append( [test_stop, f"stress tests stops on beam {test_beam}"] )
        rpt.sort()
        
        fh = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runtime.log'), 'a')
        fh.write("Completed Scheduling for UTC %s to %s\n" % (start.strftime('%Y/%m/%d %H:%M:%S'), 
                                                              stop.strftime('%Y/%m/%d %H:%M:%S')))
        fh.write("  Command:\n")
        fh.write("    %s\n" % (' '.join(cmd),))
        fh.write("  Timeline:\n")
        for t,info in rpt:
            fh.write("    %s - %s\n" % (t.strftime("%Y/%m/%d %H:%M:%S"), info))
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
