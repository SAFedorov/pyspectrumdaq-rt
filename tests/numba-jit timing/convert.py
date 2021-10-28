# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# Single channel:
# ns = 10**7
# nch = 1
# nit = 1000
# Numba-jit-serial total time (s): 16.185272932052612
# Numba-jit-parallel total time (s): 15.982435941696167
# Numpy-multiply total time (s): 15.792657613754272
#
# ns = 10**6
# nch = 1
# nit = 1000
# Numba-jit-serial total time (s): 1.5829999446868896
# Numba-jit-parallel total time (s): 1.6279191970825195
# Numpy-multiply total time (s): 1.5395128726959229
#
# ns = 10**5
# nch = 1
# nit = 10000
# Numba-jit-serial total time (s): 0.6350193023681641
# Numba-jit-parallel total time (s): 0.8131463527679443
# Numpy-multiply total time (s): 0.6260192394256592
#
# ns = 2*10**3
# nch = 1
# nit = 100000
# Numba-jit-serial total time (s): 0.16500210762023926
# Numba-jit-parallel total time (s): 9.998680353164673
# Numpy-multiply total time (s): 0.28800177574157715
#
#
# 2 channels:
# ns = 10**6
# nch = 2
# nit = 1000
# Numba-jit-serial total time (s): 6.498003721237183
# Numba-jit-parallel total time (s): 3.5624639987945557
# Numpy-multiply total time (s): 9.319601774215698
#
# ns = 10**3
# nch = 2
# nit = 100000
# Numba-jit-serial total time (s): 0.22498369216918945
# Numba-jit-parallel total time (s): 9.302517175674438
# Numpy-multiply total time (s): 0.9556634426116943
#
# ns = 10**5
# nch = 2
# nit = 10000
# Numba-jit-serial total time (s): 2.3650741577148438
# Numba-jit-parallel total time (s): 1.8508021831512451
# Numpy-multiply total time (s): 9.21491527557373
#
#
# 4 channels:
# ns = 10**6
# nch = 4
# nit = 1000
# Numba-jit-serial total time (s): 25.480729579925537
# Numba-jit-parallel total time (s): 7.02749490737915
# Numpy-multiply total time (s): 13.107496738433838
#
#

import time

import numpy as np
from numpy.random import random
import numba

@numba.jit(nopython=True)
def _convert(dst, src, scalefs):
    """All serial
    """
    for ch in range(dst.shape[1]):
        for n in range(dst.shape[0]):
            dst[n, ch] = src[n, ch] * scalefs[ch]


@numba.jit(nopython=True, parallel=True)
def _convert2(dst, src, scalefs):
    """Convert an int16 2D numpy array (nsamples, nchanels) into a 2D float64 
    numpy array using the specified conversion factors for each channel. 
    Stores the result in a preallocated destination array.

    Args:
        dst: Destination array.
        src: Source array.
        scalefs: A list of scaling factors for the channels.
    """
    for ch in numba.prange(dst.shape[1]):
        for n in numba.prange(dst.shape[0]):
            dst[n, ch] = src[n, ch] * scalefs[ch]


ns = 10**5
nch = 2

nit = 10000

src = random((ns, nch))
dst = np.zeros((ns, nch), dtype=np.float64)
cfs = np.array([0.1*i for i in range(nch)])  # Conversion factors.

_convert(dst, src, cfs)
_convert2(dst, src, cfs)

startt = time.time()

for i in range(nit):
    _convert(dst, src, cfs)

endt = time.time()
print(f"Numba-jit-serial total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    _convert2(dst, src, cfs)
endt = time.time()
print(f"Numba-jit-parallel total time (s): {endt-startt}")


startt = time.time()
for i in range(nit):
    np.multiply(src, cfs, out=dst)
endt = time.time()
print(f"Numpy-multiply total time (s): {endt-startt}")