"""Cloud type presets for the prototype, from the shared table in python/cloud_types.py."""

import os
import sys

import numpy as np

from clouds import NP, P

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import cloud_types  # noqa: E402


def layer(**kw):
    d = dict(cloud_types.DEFAULTS)
    d.update(kw)
    a = np.zeros(NP)
    for k, v in d.items():
        a[P[k]] = v
    return a


TYPES = dict((name, layer(**kw)) for name, kw in cloud_types.TYPES.items())
