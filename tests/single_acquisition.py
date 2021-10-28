from pyspectrumdaq import Card
import matplotlib.pyplot as plt

import time

with Card() as adc:
    sr = 10**6
    ns = 20 * 4096

    adc.set_acquisition(channels=[1], 
                        terminations=["1M"], 
                        fullranges=[0.2],
                        pretrig_ratio=0, 
                        nsamples=ns,
                        samplerate=sr)             
    adc.set_trigger(mode="soft")

    t = [i/sr for i in range(ns)]  # Calculates the time axis.
    data = [0 for i in range(ns)]

    ntraces = 40  # We want to acquire this number of traces and stop.
    startt = time.time()

    data_list = []
    for cnt in range(ntraces):
        data = adc.acquire()
        data_list.append(data)

endt = time.time()

dstime = ns * ntraces / sr
readtime = endt - startt
print(f"The time of data sampling: {dstime}")
print(f"The total data reading time: {readtime}")
print(f"The ratio of the two: {readtime/dstime}")

plt.plot(t, data_list[0], linestyle="none", marker="o", markersize=6)
plt.plot(t, data_list[-1], linestyle="none", marker="o", markersize=3)
plt.show()