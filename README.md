# pyspectrumdaq

A package for data acquisition using Spectrum M2 digitizer cards.
Supports multi-channel acquisition, external triggering, continuous
data streaming etc.

Includes a real-time spectrum analyzer app with a Qt UI.

## Requirements

Console usage requires:

* numpy
* numba

The spectrum analyzer app, in addition, requires:
* pyqtgraph
* pyfftw
* h5py

The package is tested with a M2i.4931-Exp card and pyqtgraph 0.11.0.

## Usage examples

A simple multi-channel usage example:

```python
from pyspectrumdaq import Card

# It is recommended to use context management ("with" statement) to ensire that 
# the card is closed when communication is over.
with Card() as adc:
    adc.set_acquisition(channels=[0, 1, 2, 3], 
                        terminations=["1M", "1M", "50", "1M"], 
                        fullranges=[2, 2, 2, 2],
                        pretrig_ratio=0, 
                        nsamples=10**6,
                        samplerate=10**6)             
    adc.set_trigger(mode="soft")

    data = adc.acquire()
    # data now contains a float64 NumPy array, shaped as [nsamples, nchannels]

    # The time stamps for the data record are calculated as
    t = [i/adc.samplerate for i in range(ns)] 
```

An example of using the card in FIFO mode for real-time data streaming:
```python
with Card() as adc:
    adc.set_acquisition(mode = "fifo_single", 
                        channels=[0], 
                        terminations=["1M"], 
                        fullranges=[2],
                        pretrig_ratio=0, 
                        nsamples=10**6,
                        samplerate=10**6)             
    adc.set_trigger(mode="soft")

    # Acquires 100 traces with no missed samples between them.
    data_list = [data[:, 0] for data in adc.fifo(100)]

    # Starts an infinite data acquisition loop.
    for data in adc.fifo():
        pass
```

Starting the spectrum analyzer app:
```python
from pyspectrumdaq import rts

if __name__ == "__main__":
    # The spectrum analyzer uses multiprocessing, so the
    # if __name__ == "__main__" idiom is required.

    rts(basedir="home", acq_settings={"clock": "ext", "ext_clock_freq"=10**7})
```
