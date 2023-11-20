#!/usr/bin/env python3

import os
import sys

from lwa_auth import KEYS as LWA_AUTH_KEYS
from lwa_auth.signed_requests import post as signed_post

URL = "https://lwalab.phys.unm.edu/OpScreen/update"


def main(args):
    for site in ('lwa1', 'lwasv', 'lwana'):
        with open('metric-%s' % site, 'r') as fh:
            for line in fh:
                line = line.strip().rstrip()
            line = line.split()
            line = ';;;'.join(line)
            
            f = signed_post(LWA_AUTH_KEYS.get('lwaucf', kind='private'), URL,
                            data={'site': site, 'subsystem': 'SEFD', 'data': line})
            f.close()

    p = os.path.dirname(os.path.abspath(__file__))
    os.system(os.path.join(p, 'influxSEFD.py'))
    os.system(os.path.join(p, 'influxSEFD_SV.py'))
    os.system(os.path.join(p, 'influxSEFD_NA.py'))


if __name__ == '__main__':
    main(sys.argv[1:])
