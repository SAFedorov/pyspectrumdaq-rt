# Conclusions: A robust factor of >4 gain for serial implementation. The 
# parallel implementation behaves less reliably and can perform somewhat better 
# or worse than the serial one (it probably requres some cash to be faster).
#
# Representative results obtained with numba 0.53.1 and numpy 1.21.2 (2021-10):
#
# ns = 2*10**5
# nit = 10000
# 
# Numba-jit-serial total time: 1.1804018020629883
# Numba-jit-parallel total time: 0.8450229167938232
# Numpy total time: 9.185407638549805
# Numpy-add total time: 10.321401834487915

import time

import numpy as np
import numba

from numba.types import float64, CPointer, void, intp, int32


@numba.jit(nopython=True)
def _addarr(dst, src):
    """Serial version"""
    for i in range(dst.shape[0]):
        dst[i] = dst[i] + src[i, 0]


@numba.jit(nopython=True, parallel=True)
def _addarrp(dst, src):
    """Parallel version"""
    for i in numba.prange(dst.shape[0]):
        dst[i] = dst[i] + src[i, 0]

ns = 2*10**5
nit = 10000

src = np.random.random((ns, 1))
dst = np.zeros(ns, dtype=np.float64)

# Call the functions once before timing to trigger their compilation.
_addarr(dst, src)
_addarrp(dst, src)

startt = time.time()
for i in range(nit):
    _addarr(dst, src)
endt = time.time()
print(f"Numba-jit-serial total time: {endt-startt}")


startt = time.time()
for i in range(nit):
    _addarrp(dst, src)
endt = time.time()
print(f"Numba-jit-parallel total time: {endt-startt}")


startt = time.time()
for i in range(nit):
    dst[:] = dst + src[:, 0]
endt = time.time()
print(f"Numpy total time: {endt-startt}")


for i in range(nit):
    np.add(dst, src[:, 0], out=dst)
endt = time.time()
print(f"Numpy-add total time: {endt-startt}")