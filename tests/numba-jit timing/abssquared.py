# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# ns = 2*10**5
# nit = 10000
#
# Numba-jit-serial total time (s): 6.6879496574401855
# Numba-jit-parallel total time (s): 2.7104570865631104
# Numba-jit-serial-mem-alloc total time (s): 6.883003234863281
# Numba-jit-parallel-mem-alloc total time (s): 2.387998342514038
# Numba-jit-serial-psd total time (s): 6.447001934051514
# Numba-jit-parallel-psd total time (s): 2.3609981536865234
# Numba-jit-serial-psd real**2 + imag**2 total time (s): 0.6980221271514893
# Numba-jit-parallel-psd real**2 + imag**2 total time (s): 0.45098066329956055
# Numpy np.square(np.abs()) total time (s): 11.953019142150879
# Numpy .real**2 + .imag**2 total time (s): 10.594467639923096
# FFT time (s): 52.506983518600464
#
#
# ns = 2*10**3
# nit = 100000
#
# Numba-jit-serial total time (s): 0.8448688983917236
# Numba-jit-parallel total time (s): 9.91997742652893
# Numba-jit-serial-mem-alloc total time (s): 0.84902024269104
# Numba-jit-parallel-mem-alloc total time (s): 9.188977718353271
# Numba-jit-serial-psd total time (s): 0.7130169868469238
# Numba-jit-parallel-psd total time (s): 11.454984664916992
# Numba-jit-serial-psd real**2 + imag**2 total time (s): 0.15899968147277832
# Numba-jit-parallel-psd real**2 + imag**2 total time (s): 10.980000972747803
# Numpy np.square(np.abs()) total time (s): 1.1550140380859375
# Numpy .real**2 + .imag**2 total time (s): 0.5710041522979736
# FFT time (s): 2.4680042266845703

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


@numba.jit(nopython=True)
def _psd(dst, src):
    """One-sided psd, serial."""
    for i in range(src.shape[0] // 2):
        dst[i] = abs(src[i] * src[i])
    
    dst[0] = abs(src[0] * src[0]) / 2


@numba.jit(nopython=True, parallel=True)
def _psdp(dst, src):
    """One-sided psd, parallel."""
    for i in numba.prange(src.shape[0] // 2):
        dst[i] = abs(src[i] * src[i])
    
    dst[0] = abs(src[0] * src[0]) / 2


@numba.jit(nopython=True)
def _psd2(dst, src):
    """One-sided psd, serial."""
    for i in range(src.shape[0] // 2):
        dst[i] = src[i].real ** 2 + src[i].imag ** 2
    
    dst[0] = abs(src[0] * src[0]) / 2


@numba.jit(nopython=True, parallel=True)
def _psd2p(dst, src):
    """One-sided psd, parallel."""
    for i in numba.prange(src.shape[0] // 2):
        dst[i] = src[i].real ** 2 + src[i].imag ** 2
    
    dst[0] = abs(src[0] * src[0]) / 2


ns = 2*10**3
nit = 100000

src = random((ns, 1))
dst = np.zeros(ns // 2, dtype=np.float64)


_abssquared(dst)
_abssquaredp(dst)
_abssquared2(dst, rfft(src[:, 0]))
_abssquared2p(dst, rfft(src[:, 0]))
_psd(dst, rfft(src[:, 0]))
_psdp(dst, rfft(src[:, 0]))
_psd2(dst, rfft(src[:, 0]))
_psd2p(dst, rfft(src[:, 0]))

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
    _psd(dst, y)
endt = time.time()
print(f"Numba-jit-serial-psd total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _psdp(dst, y)
endt = time.time()
print(f"Numba-jit-parallel-psd total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _psd2(dst, y)
endt = time.time()
print(f"Numba-jit-serial-psd real**2 + imag**2 total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _psd2p(dst, y)
endt = time.time()
print(f"Numba-jit-parallel-psd real**2 + imag**2 total time (s): {endt-startt}")


startt = time.time()
y2 = y[0 : ns // 2]
for i in range(nit):
    dst = np.square(np.abs(y[0 : ns // 2]))
endt = time.time()
print(f"Numpy np.square(np.abs()) total time (s): {endt-startt}")


startt = time.time()
y2 = y[0 : ns // 2]
for i in range(nit):
    dst = y2.real ** 2 + y2.imag ** 2
endt = time.time()
print(f"Numpy .real**2 + .imag**2 total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    y = rfft(src[:, 0])
endt = time.time()
print(f"FFT time (s): {endt-startt}")
