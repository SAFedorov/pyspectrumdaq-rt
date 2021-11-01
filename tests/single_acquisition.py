from pyspectrumdaq import Card
import matplotlib.pyplot as plt

import time

with Card() as adc:
    sr = 30 * 10**6
    ns = 409600

    adc.set_acquisition(channels=[1], 
                        terminations=["1M"], 
                        fullranges=[0.2],
                        pretrig_ratio=0, 
                        nsamples=ns,
                        samplerate=sr)             
    adc.set_trigger(mode="soft")

    ntraces = 40  # The number of traces to acquire.
    dstime = ns * ntraces / adc.samplerate  # The total pure duration of data.
    t = [i/adc.samplerate for i in range(ns)]  # The time axis.

    startt = time.time()

    data_list = []
    for cnt in range(ntraces):
        data = adc.acquire()
        data_list.append(data)

endt = time.time()

readtime = endt - startt
print(f"The time of data sampling: {dstime}")
print(f"The total data reading time: {readtime}")
print(f"The ratio of the two: {readtime/dstime}")

plt.plot(t, data_list[0], linestyle="none", marker="o", markersize=6)
plt.plot(t, data_list[-1], linestyle="none", marker="o", markersize=3)
plt.show()