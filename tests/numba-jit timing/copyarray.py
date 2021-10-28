# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# ns = 2*10**5
# nit = 10000
# Numba-jit-serial total time (s): 1.2929890155792236
# Numba-jit-parallel total time (s): 0.8566210269927979
# Numpy total time: 1.0520060062408447
#
#
# ns = 2*10**6
# nit = 1000
# Numba-jit-serial total time (s): 3.533703327178955
# Numba-jit-parallel total time (s): 3.482008457183838
# Numpy total time: 2.1353394985198975

import time

import numpy as np
from numpy.random import random
import numba


@numba.jit(nopython=True)
def _copyarray(dst, src):
    """A serial implementation."""
    for i in range(dst.shape[0]):
        dst[i] = src[i, 0]


@numba.jit(nopython=True, parallel=True)
def _copyarrayp(dst, src):
    """A parallel implementation."""
    for i in numba.prange(dst.shape[0]):
        dst[i] = src[i, 0]


ns = 2*10**5
nit = 10000

src = random((ns, 1))
dst = np.zeros(ns, dtype=np.float64)

_copyarray(dst, src)
_copyarrayp(dst, src)

startt = time.time()
for i in range(nit):
    _copyarray(dst, src)
endt = time.time()
print(f"Numba-jit-serial total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _copyarrayp(dst, src)
endt = time.time()
print(f"Numba-jit-parallel total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    dst[:] = src[:, 0]
endt = time.time()
print(f"Numpy total time: {endt-startt}")