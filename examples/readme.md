The content of this folder:
* `daq.py` - a module with some functions for data acquisition and the calculation of power spectral densities.
    ```python
    from daq import acq, psd
    
    traces, dt = acq(10)
    freq, psd = psd(traces, dt)
    ```
* `spectrum_analyzer.py` - a script to start the spectrum analyzer app with a pre-set configuration.
* `Sepctrum.bat` - a bat file to call `spectrum_analyzer.py` from windows desktop, assuming `pyspectrumdaq` package is installed on an anaconda environment `myenv` of the user `UserName`.