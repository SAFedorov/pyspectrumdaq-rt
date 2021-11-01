from pyspectrumdaq import Card
import matplotlib.pyplot as plt

import numpy as np

import time

with Card() as adc:
    sr = 30 * 10**6
    ns = 409600

    adc.set_acquisition(mode = "fifo_single", 
                        channels=[1], 
                        terminations=["1M"], 
                        fullranges=[5],
                        pretrig_ratio=0, 
                        nsamples=ns,
                        samplerate=sr)             
    adc.set_trigger(mode="soft")

    ntraces = 100  # The number of traces to acquire.
    dt_trace = ns / adc.samplerate  # The duration of one trace.
    dt_sampling = dt_trace * ntraces  # The total pure duration of data.
    t = np.array([i/adc.samplerate for i in range(ns)])  # The time axis.

    startt = time.time()
    data_list = [data[:, 0] for data in adc.fifo(ntraces)]
    endt = time.time()

dt_read = endt - startt
print(f"The time of data sampling: {dt_sampling}")
print(f"The total data reading time: {dt_read}")

print(f"The ratio of the two: {dt_read/dt_sampling}")
# Gives about 1.003 for 55 sec data streaming at 30 MHz sampling rate.

# The joinings of two curves are continuous to show that no samples are missing.
plt.plot(t[-100:], data_list[-2][-100:], 
         linestyle="-", marker="o", markersize=3)
plt.plot(t[:100] + dt_trace, data_list[-1][:100], 
         linestyle="--", marker="o", markersize=3)
plt.show()