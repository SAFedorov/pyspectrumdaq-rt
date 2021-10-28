# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# ns = 10**6
# n = 100
#
# nit = 40000
#
# Numba-jit-serial total time: 0.0279998779296875
# Numba-jit-parallel total time: 3.6699724197387695
# Numpy total time: 1.408250331878662

import time

import numpy as np
from numpy.random import random
import numba


@numba.jit(nopython=True)
def _downsample(dst, src, n):
    """Serial implementation."""
    l = dst.shape[0] // n
    for i in range(l):
        dst[i] = src[n*i, 0]


@numba.jit(nopython=True, parallel=True)
def _downsamplep(dst, src, n):
    """Parallel implementation."""
    l = dst.shape[0] // n
    for i in numba.prange(l):
        dst[i] = src[n*i, 0]


ns = 10**6
n = 100

nit = 40000

src = random((ns, 1))
dst = np.zeros(ns // n, dtype=np.float64)

_downsample(dst, src, n)
_downsamplep(dst, src, n)

startt = time.time()
for i in range(nit):
    _downsample(dst, src, n)
endt = time.time()
print(f"Numba-jit-serial total time: {endt-startt}")


startt = time.time()
for i in range(nit):
    _downsamplep(dst, src, n)
endt = time.time()
print(f"Numba-jit-parallel total time: {endt-startt}")


startt = time.time()
for i in range(nit):
    dst[:] = src[::n, 0]
endt = time.time()
print(f"Numpy total time: {endt-startt}")