# Representative results obtained with fftw 3.3.10 and numpy 1.21.2 (2021-10):
#
# ns = 2*10**5
# nit = 1000
#
# FFTW with FFTW_ESTIMATE time (s): 1.4090220928192139. Startup-time (s): 0.005998849868774414.
# FFTW with FFTW_MEASURE time (s): 1.3480050563812256. Startup-time (s): 4.902997732162476.
# FFTW with FFTW_EXHAUSTIVE time (s): 1.405996322631836. Startup-time (s): 468.7189145088196.
# Numpy FFT time (s): 4.9393088817596436


import time

from numpy.fft import rfft
from numpy.random import random

import pyfftw


ns = 2*10**5
nit = 1000

src = random(ns)


a = pyfftw.empty_aligned(ns, dtype='float64')
a2 = pyfftw.empty_aligned(ns, dtype='float64')
a3 = pyfftw.empty_aligned(ns, dtype='float64')
b = pyfftw.empty_aligned(ns // 2 + 1, dtype='complex128')


startt = time.time()
fft_object_est = pyfftw.FFTW(a, b, flags=['FFTW_ESTIMATE'])
midt = time.time()
for i in range(nit):
    a[:] = src
    fft_object_est()
endt = time.time()
print(f"FFTW with FFTW_ESTIMATE time (s): {endt-midt}. Startup-time (s): {midt-startt}.")


startt = time.time()
fft_object_meas = pyfftw.FFTW(a2, b, flags=['FFTW_MEASURE'])
midt = time.time()
for i in range(nit):
    a2[:] = src
    fft_object_meas()
endt = time.time()
print(f"FFTW with FFTW_MEASURE time (s): {endt-midt}. Startup-time (s): {midt-startt}.")


startt = time.time()
fft_object_est = pyfftw.FFTW(a, b, flags=['FFTW_EXHAUSTIVE'])
midt = time.time()
for i in range(nit):
    a[:] = src
    fft_object_est()
endt = time.time()
print(f"FFTW with FFTW_EXHAUSTIVE time (s): {endt-midt}. Startup-time (s): {midt-startt}.")


startt = time.time()
for i in range(nit):
    y = rfft(src)
endt = time.time()
print(f"Numpy FFT time (s): {endt-startt}")
