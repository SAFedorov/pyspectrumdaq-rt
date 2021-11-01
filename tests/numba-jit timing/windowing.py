# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# ns = 2*10**5
# nit = 10000
#
# Window numba-jit-serialtotal time (s): 1.1740193367004395
# Window numba-jit-parallel total time (s): 1.205984115600586
# Window np.divide total time (s): 2.913020133972168
# Spectral windowing numba-jit-serial total time (s): 14.312008142471313
# Spectral windowing numba-jit-parallel total time (s): 4.132978200912476
# Numpy FFT time (s): 53.60099816322327
#
#
# ns = 2*10**3
# nit = 100000
#
# Window numba-jit-serial total time (s): 0.12299633026123047
# Window numba-jit-parallel total time (s): 0.12602901458740234
# Window np.divide total time (s): 0.4849870204925537
# Spectral windowing numba-jit-serial total time (s): 1.5320169925689697
# Spectral windowing numba-jit-parallel total time (s): 8.388999462127686
# Numpy FFT time (s): 2.312020778656006


import time

import numpy as np
from numpy.random import random
import numba

from numpy.fft import rfft


@numba.njit
def apply_window_serial(a, b):
    """The serial implementation of apply_window."""
    for i in range(a.shape[0]):
        a[i] = a[i] * b[i]


@numba.njit
def apply_window_parallel(a, b):
    """The parallel implementation of apply_window."""
    for i in numba.prange(a.shape[0]):
        a[i] = a[i] * b[i]


@numba.njit
def calc_windowed_psd_serial(a, b):
    """The serial implementation of calc_windowed_psd."""

    for i in range(1, a.shape[0] - 1):
        a[i] = (4 / 3) * abs(b[i] - 0.5 * b[i + 1] - 0.5 * b[i - 1]) ** 2

    # Uses the property of DFT: X[m] = conj(X[N-m])
    a[0] = (2 / 3) * abs(b[0] - np.real(b[1])) ** 2
    a[-1] = (4 / 3) * abs(b[-1] - np.real(b[-2])) ** 2


@numba.njit(parallel=True)
def calc_windowed_psd_parallel(a, b):
    """The parallel implementation of calc_windowed_psd."""

    for i in numba.prange(1, a.shape[0] - 1):
        a[i] = (4 / 3) * abs(b[i] - 0.5 * b[i + 1] - 0.5 * b[i - 1]) ** 2

    # Uses the property of DFT: X[m] = conj(X[N-m])
    a[0] = (2 / 3) * abs(b[0] - np.real(b[1])) ** 2
    a[-1] = (4 / 3) * abs(b[-1] - np.real(b[-2])) ** 2


ns = 2*10**3
nit = 100000

yt = random(ns)
yf = rfft(yt)[0 : ns // 2]

# The Hann window function w[n] = cos(2*pi*n/N)**2.
w = np.cos(np.linspace(0, 2 * np.pi, ns, endpoint=False)) ** 2
w = w / np.sqrt(np.sum(w ** 2))

dst = np.zeros(ns // 2, dtype=np.float64)


apply_window_serial(yt, w)
apply_window_parallel(yt, w)
calc_windowed_psd_serial(dst, yf)
calc_windowed_psd_parallel(dst, yf)

startt = time.time()
for i in range(nit):
    apply_window_serial(yt, w)
endt = time.time()
print(f"Window numba-jit-serial total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    apply_window_parallel(yt, w)
endt = time.time()
print(f"Window numba-jit-parallel total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    np.divide(yt, w, out=yt)
endt = time.time()
print(f"Window np.divide total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    calc_windowed_psd_serial(dst, yf)
endt = time.time()
print(f"Spectral windowing numba-jit-serial total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    calc_windowed_psd_parallel(dst, yf)
endt = time.time()
print(f"Spectral windowing numba-jit-parallel total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    yf = rfft(yt)
endt = time.time()
print(f"Numpy FFT time (s): {endt-startt}")
