#!/usr/bin/env python3

import os
import sys
import json
from datetime import datetime

from lwa_auth import KEYS as LWA_AUTH_KEYS
from lwa_auth.signed_requests import post as signed_post

URL = "https://lwalab.phys.unm.edu/OpScreen/update"


def _serialize_datetime(value):
    try:
        return value.isoformat()
        except AttributeError:
    return value


def main(args):
    for site in ('lwa1', 'lwasv', 'lwana'):
        with open('metric-%s' % site, 'r') as fh:
            for line in fh:
                line = line.strip().rstrip()
            line = line.split()
            
            data = []
            data.append({'source':     line[0],
                         'zenith_ang': line[3],
                         'frequency':  float(line[4]),
                         'err_ra':     line[5],
                         'err_dec':    line[6],
                         'sefd':       float(line[7]),
                         'fwhm':       line[8],
                         'updated':    datetime.strptime(f"{line[1]} {line[2]}", "%Y/%m/%d %H:%M:%S")})
            
            out = json.dumps(data, default=_serialize_datetime)
            f = signed_post(LWA_AUTH_KEYS.get('lwaucf', kind='private'), URL,
                            data={'site': site, 'subsystem': 'SEFD', 'data': out})
            f.close()
            
    p = os.path.dirname(os.path.abspath(__file__))
    os.system(os.path.join(p, 'influxSEFD.py'))
    os.system(os.path.join(p, 'influxSEFD_SV.py'))
    os.system(os.path.join(p, 'influxSEFD_NA.py'))


if __name__ == '__main__':
    main(sys.argv[1:])
