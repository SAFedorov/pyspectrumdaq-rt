# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# ns = 2*10**5
# nit = 10000
#
# Numba-jit-serial total time (s): 5.771999835968018
# Numba-jit-parallel total time (s): 2.6425814628601074
# Numba-jit-serial-mem-alloc total time (s): 5.964021921157837
# Numba-jit-parallel-mem-alloc total time (s): 2.3881945610046387
# Numpy total time (s): 10.97267746925354
# FFT time (s): 47.9365873336792
#
#
# ns = 2*10**3
# nit = 100000
#
# Numba-jit-serial total time (s): 0.8354270458221436
# Numba-jit-parallel total time (s): 9.508841514587402
# Numba-jit-serial-mem-alloc total time (s): 0.7359964847564697
# Numba-jit-parallel-mem-alloc total time (s): 9.258419752120972
# Numpy total time (s): 1.1371526718139648
# FFT time (s): 2.6162519454956055

import time

import numpy as np
from numpy.random import random
import numba

from numpy.fft import rfft


@numba.jit(nopython=True)
def _abssquared(src):
    """A serial version."""
    for i in range(src.shape[0] // 2):
        src[i] = abs(src[i] * src[i])


@numba.jit(nopython=True, parallel=True)
def _abssquaredp(src):
    """A parallel version."""
    for i in numba.prange(src.shape[0] // 2):
        src[i] = abs(src[i] * src[i])


@numba.jit(nopython=True)
def _abssquared2(dst, src):
    """A serial version with memory pre-allocation."""
    for i in range(src.shape[0] // 2):
        dst[i] = abs(src[i] * src[i])


@numba.jit(nopython=True, parallel=True)
def _abssquared2p(dst, src):
    """A parallel version with memory pre-allocation."""
    for i in numba.prange(src.shape[0] // 2):
        dst[i] = abs(src[i] * src[i])


ns = 2*10**5
nit = 10000

src = random((ns, 1))
dst = np.zeros(ns // 2, dtype=np.float64)


_abssquared(dst)
_abssquaredp(dst)
_abssquared2(dst, rfft(src[:, 0]))
_abssquared2p(dst, rfft(src[:, 0]))

y = rfft(src[:, 0])

startt = time.time()
for i in range(nit):
    _abssquared(y)
endt = time.time()
print(f"Numba-jit-serial total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _abssquaredp(y)
endt = time.time()
print(f"Numba-jit-parallel total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _abssquared2(dst, y)
endt = time.time()
print(f"Numba-jit-serial-mem-alloc total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _abssquared2p(dst, y)
endt = time.time()
print(f"Numba-jit-parallel-mem-alloc total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    dst = np.square(np.abs(y[0 : ns // 2]))
endt = time.time()
print(f"Numpy total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    y = rfft(src[:, 0])
endt = time.time()
print(f"FFT time (s): {endt-startt}")
