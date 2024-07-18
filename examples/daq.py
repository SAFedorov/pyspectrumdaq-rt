from typing import Union

import numpy as np
from numpy import pi

import h5py

from pyspectrumdaq import Card
from scipy import signal

from datetime import datetime
from matplotlib import pyplot as plt


def psd(traces: list, dt: float = 1., window: str = "Hann") -> tuple:
    """Calculates the two-sided power spectral density from a list 
    of data traces.
    
    Args:
        traces:
            A list of numpy arrays of the shape (nchannels, nsamples).
        dt:
            Time step between samples in seconds.
        window:
            Windowing function to be applied to the data. Anything but "Hann"
            is no windowing.    
    
    Returns:
        Tuple (freqs, psd1, ..., psdn), where 1, ..., n are the channels.
    """

    ns = traces[0].shape[-1]
    if isinstance(window, str) and window.lower() == "hann":
        w = np.sqrt(8 / 3) * np.sin(np.linspace(0, pi, ns, endpoint=False)) ** 2
        traces = [tr * w for tr in traces]

    nf = ns  # The number of frequency bins is the same 
             # as the number of samples.
    sp = np.zeros(traces[0].shape)
    
    for tr in traces:
        sp += np.abs(np.fft.ifft(tr, axis=-1))**2  
        # Inverse FFT is to be consistent with the physicist's convention.
    
    sp = sp/(len(traces) * nf)
    sp = np.concatenate((sp[nf//2+1:], sp[:nf//2+1]))
    
    # Frequency axis in Hz.
    fs = np.array([i/(nf*dt) for i in range(-nf//2, nf//2)])
    
    return (fs, *sp)


def psdcorr(traces: list, dt: float = 1., window: str = "Hann") -> tuple:
    """Calculates the two-sided power spectral densities and 
    the cross-correlation for a list of traces acquired from two channels.
    
    Args:
        traces:
            A list of numpy arrays of the shape (2, nsamples).
        dt:
            Time step between samples in seconds.
        window:
            Windowing function to be applied to the data. Anything but "Hann"
            is no windowing.    
    
    Returns:
        Tuple (freqs, psd1, psd2, corr12).
    """

    if traces[0].shape[0] != 2:
        raise ValueError("traces must be a list of arrays recorded from "
                         "two channels and shaped as (2, nsamples). "
                         f"The current shape is {traces[0].shape}.")

    ns = traces[0].shape[-1]
    if isinstance(window, str) and window.lower() == "hann":
        w = np.sqrt(8 / 3) * np.sin(np.linspace(0, pi, ns, endpoint=False)) ** 2
        traces = [tr * w for tr in traces]

    nf = ns  # The number of frequency bins is the same 
             # as the number of samples.
    sp = np.zeros((2, nf))
    corr = np.zeros((nf,))
    
    for tr in traces:
        ft = np.fft.ifft(tr, axis=-1)
        # Inverse FFT is to be consistent with the physicist's convention.

        sp += np.abs(ft)**2
        corr += ft[0].conj() * ft[1]
    
    sp = sp/(len(traces) * nf)
    sp = np.concatenate((sp[nf//2+1:], sp[:nf//2+1]))

    corr = corr/(len(traces) * nf)
    corr = np.concatenate((corr[nf//2+1:], corr[:nf//2+1]))
    
    # Frequency axis in Hz.
    fs = np.array([i/(nf*dt) for i in range(-nf//2, nf//2)])
    
    return (fs, sp[0], sp[1], corr)


def defaults() -> dict:
    """Default card settings."""

    settings = dict(mode="std_single",
                    channels=[1],           # Numbers of the active DAQ channel.
                    terminations=["50"],    # Channel terminations.
                    fullranges=[2],         # Channel full ranges.
                    pretrig_ratio=0.,       # No data from prior to the trigger. 
                    nsamples=100 * 10**6,   # Number of samples in a trace.
                    samplerate=15 * 10**6,  # DAQ sampling rate.
                    trig_mode="soft")       # Trigger. Use "soft" for 
                                            # free-running acquisition and "ext"
                                            # for externally-triggered.
    return settings


def acq(n: int, 
        save: bool = False, 
        settings: Union[dict, None] = None) -> list:
    
    """Acquires `n` traces from the card initialized with `settings` 
    and saves them in the current folder if `save` is `True`. Works for 
    single and multiple channels.

    Args:
        n: The number of traces to be acquired.
        save: If the traces should be saved.
        settings: Dictionary of card settings.
    
    Returns:
        Tuple (list of traces, dt).
    """

    if settings:
        settings = dict(defaults(), **settings)
    else:
        settings = defaults()
    
    trig_mode = settings.pop("trig_mode")
    dt = 1 / settings["samplerate"]

    with Card() as adc:
        adc.set_acquisition(**settings)          
        adc.set_trigger(mode=trig_mode)        
        
        traces = []
        
        for _ in range(n):
            sig = adc.acquire().T  # shape (nchannels, nsamples)
            traces.append(sig)
        
        if save:    
            # Saves the data in an HDF5 file in the current directory. 
            file_name = str(datetime.now()).replace(':', '-') + ".h5"
            with h5py.File(file_name, "w") as f:
                f["ydata"] = np.array(traces)
                f["ydata"].attrs["xmin"] = 0
                f["ydata"].attrs["dx"] = dt
                f["ydata"].attrs["ntraces"] = n
                
        return traces


def acqdemod(n: int, 
             save: bool = False, 
             fdemod: float = 0.94e6,
             flp: float = 10**5,
             plotfft: bool = True, 
             settings: Union[dict, None] = None) -> list:
    
    """Acquires `n` demodulated traces from the card initialized with `settings` 
    and saves them in the current folder if `save` is `True`. Works for 
    single and multiple channels.

    Args:
        n: The number of traces to be acquired.
        save: If the traces should be saved.
        fdemod: Demodulation frequency in Hz.
        flp: Lowpass frequency in Hz. It is also used to determine 
            the downsampling ratio.
        plotfft: If the power spectral densities of the signals should 
            be plotted after the acquisition.
        settings: Dictionary of card settings.
    
    Returns:
        Tuple (list of traces, dt).
    """

    if settings:
        settings = dict(defaults(), **settings)
    else:
        settings = defaults()

    trig_mode = settings.pop("trig_mode")
    nsamples = settings["nsamples"]
    samplerate = settings["samplerate"]

    with Card() as adc:
        adc.set_acquisition(**settings)             
        adc.set_trigger(mode=trig_mode)

        # The low-pass filter.
        sos = signal.butter(6, flp, btype="lowpass", fs=samplerate, 
                            output="sos", analog=False)
        
        # The demodulation exponent.
        dt = 1 / samplerate
        t = np.array([i * dt for i in range(nsamples)]) 
        exp_tr = np.exp(2j * pi * fdemod * t)
        
        samplerate_ratio = samplerate // (6 * flp)
        traces = []
        
        for _ in range(n):
            sig = adc.acquire().T  # shape (nchannels, nsamples)
            
            # Demodulates, filters and downsamples.
            sig = sig * exp_tr
            sig = signal.sosfilt(sos, sig, axis=-1)
            sig = sig[:, ::samplerate_ratio]
            
            traces.append(sig)
        
        dt_ds = dt * samplerate_ratio

        if save:    
            # Saves the data in an HDF5 file in the current directory. 
            file_name = str(datetime.now()).replace(':', '-') + " demod.h5"
            with h5py.File(file_name, "w") as f:
                f["ydata"] = np.array(traces)
                f["ydata"].attrs["xmin"] = 0
                f["ydata"].attrs["dx"] = dt_ds
                f["ydata"].attrs["ntraces"] = n
        
        if plotfft:            
            plt.plot(*psd(traces, dt=dt_ds))
            plt.yscale("log")
                
        return traces, dt_ds