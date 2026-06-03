#!/usr/bin/env python3

import os
import sys
import json
import math
import ephem
from datetime import datetime, timezone

from lwa_auth import KEYS as LWA_AUTH_KEYS
from lwa_auth.signed_requests import post as signed_post

URL = "https://lwalab.phys.unm.edu/OpScreen/update"


def _serialize_datetime(value):
    try:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.isoformat() + 'Z'
    except AttributeError:
        return value


def main(args):
    for site in ('lwa1', 'lwasv', 'lwana'):
        with open('metric-%s' % site, 'r') as fh:
            for line in fh:
                line = line.strip().rstrip()
            line = line.split()
            
            fit_flag = ''
            try:
                fwhm = ephem.degrees(line[8])
                if fwhm >= 4*math.pi:
                    fit_flag = 'RA only fit'
                elif fwhm >= 2*math.pi:
                    fit_flag = 'dec. only fit'
                elif fwhm <= 0 or fwhm != fwhm:
                    fit_flag = 'fitting failed'
            except ValueError:
                pass
                
            data = []
            data.append({'source':     line[0],
                         'zenith_ang': line[4],
                         'frequency':  float(line[3]),
                         'err_ra':     line[5],
                         'err_dec':    line[6],
                         'sefd':       float(line[7]),
                         'fwhm':       line[8],
                         'fit_flag':   fit_flag,
                         'updated':    datetime.strptime(f"{line[1]} {line[2]}", "%Y/%m/%d %H:%M:%S")})
            
            out = json.dumps(data, default=_serialize_datetime)
            f = signed_post(LWA_AUTH_KEYS.get('lwaucf', kind='private'), URL,
                            data={'site': site, 'subsystem': 'SEFD', 'data': out})
            f.close()


if __name__ == '__main__':
    main(sys.argv[1:])
