
# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# ns = 2*10**7
# nit = 100
# a = 10
#
# Numba-jit-serial total time (s): 9.467210054397583
# Numba-jit-parallel total time (s): 2.2950005531311035
# Numba-jit-serial-mem-alloc total time (s): 9.976002931594849
# Numba-jit-parallel-mem-alloc total time (s): 3.292997360229492
# Numpy total time (s): 5.253016233444214
#
#
# ns = 2*10**5
# nit = 10000
# a = 10
#
# Numba-jit-serial total time (s): 6.008684396743774
# Numba-jit-parallel total time (s): 1.3093721866607666
# Numba-jit-serial-mem-alloc total time (s): 5.40458345413208
# Numba-jit-parallel-mem-alloc total time (s): 1.3021554946899414
# Numpy total time (s): 2.99794602394104
#
#
# ns = 2*10**3
# nit = 100000
# a = 10
#
# Numba-jit-serial total time (s): 0.8348808288574219
# Numba-jit-parallel total time (s): 9.871706485748291
# Numba-jit-serial-mem-alloc total time (s): 0.6763503551483154
# Numba-jit-parallel-mem-alloc total time (s): 9.235614538192749
# Numpy total time (s): 0.5091900825500488

import time

import numpy as np

from numpy.random import random
import numba


@numba.jit(nopython=True)
def _normalize(src, a):
    """A serial version."""
    for i in range(src.shape[0]):
        src[i] = src[i] / a


@numba.jit(nopython=True, parallel=True)
def _normalizep(src, a):
    """A parallel version."""
    for i in numba.prange(src.shape[0]):
        src[i] = src[i] / a


@numba.jit(nopython=True)
def _normalize2(dst, src, a):
    """A serial version with memory pre-allocation."""
    for i in range(dst.shape[0]):
        dst[i] = src[i] / a


@numba.jit(nopython=True, parallel=True)
def _normalize2p(dst, src, a):
    """A parallel version with memory pre-allocation."""
    for i in numba.prange(dst.shape[0]):
        dst[i] = src[i] / a


ns = 2*10**7
nit = 100
a = 10


src = random(ns)
dst = np.zeros(ns, dtype=np.float64)


# Calls the functions once to trigger their compilation.
_normalize(src, a)
_normalizep(src, a)
_normalize2(dst, src, a)
_normalize2p(dst, src, a)


startt = time.time()
for i in range(nit):
    _normalize(src, a)
endt = time.time()
print(f"Numba-jit-serial total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _normalizep(src, a)
endt = time.time()
print(f"Numba-jit-parallel total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _normalize2(dst, src, a)
endt = time.time()
print(f"Numba-jit-serial-mem-alloc total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _normalize2p(dst, src, a)
endt = time.time()
print(f"Numba-jit-parallel-mem-alloc total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    np.divide(src, a, out=src)
endt = time.time()
print(f"Numpy total time (s): {endt-startt}")