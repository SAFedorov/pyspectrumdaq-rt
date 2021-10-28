from typing import Union, Sequence
from time import time
from math import ceil

from multiprocessing import Process
from multiprocessing import Value
from multiprocessing import Array
from multiprocessing import Pipe

import numpy as np

from numba import njit
from numba import prange

from pyfftw import FFTW
from pyfftw import empty_aligned

from pyqtgraph import mkQApp
from pyqtgraph.Qt import QtCore
from pyqtgraph.Qt import QtGui

from .rtsui import Ui_RtsWidget

from .card import Card
#from dummy_card import DummyCard as Card  #TODO: remove


TDSF = 100  # The shrinking factor for time-domain data.
COMM_POLL_INTVL = 0.5  # (seconds)
RT_NOT_INTVL = 15  # (seconds)


def daq_loop(card_args: list, conn, buff, buff_acc, buff_t, cnt, navg, navg_completed) -> None:
    """ Starts continuous data streaming from the card. 
    """
    init = True

    with Card(*card_args) as adc:    
        while True:
            msg = conn.recv()

            # The message can be a request to stop or new settings.
            if msg == "stop":
                cnt.value = 0
                break

            settings = msg

            navg_rt = settings.pop("navg_rt")
            trig_mode = settings.pop("trig_mode")

            adc.reset()
            
            # TODO: set clock mode before setting acquisition.
            adc.set_acquisition(**settings)
            adc.set_trigger(trig_mode)

            conn.send({"samplerate": adc.samplerate, "nsamples": adc.nsamples})

            ns = adc.nsamples
            sr = adc.samplerate
            nf = ns // 2 + 1  # The number of frequency bins.
            nst = ns // TDSF  # The number of samples in the time-domain trace.

            if init:
                npbuff = [np.ndarray((nf,), dtype=np.float64, buffer=a.get_obj()) for a in buff]
                npbuff_acc = np.ndarray((nf,), dtype=np.float64, buffer=buff_acc)
                npbuff_t = [np.ndarray((nst,), dtype=np.float64, buffer=a) for a in buff_t]
                
                nbuff = len(buff)  # The size of the interprocess buffer in traces.

                # Auxiliary arrays for the calcualtion of FFT.
                a = empty_aligned(2 * (nf - 1), dtype="float64")
                b = empty_aligned(nf, dtype="complex128")
                
                calc_fft = FFTW(a, b, flags=["FFTW_ESTIMATE"])
                # Using FFTW_ESTIMATE flag significantly reduces startup time at 
                # the expense of a less than 5 % reduction in speed according to the tests.
                
                y = np.zeros(nf, dtype=np.float64)  # A buffer to store abs spectrum squared.

                init = False

            j = 0  # The fast accumulation counter.
            cnt.value = 0  # The number of acquired traces TODO: divided by navg_rt
            navg_completed.value = 0

            dt_trace = ns / sr  # The duration of one trace (seconds).

            n_comm_poll = max(int(COMM_POLL_INTVL / dt_trace / navg_rt), 1)
            # Polling the connection is time consuming, and also it breaks 
            # if polled too frequently, so we only do it once every
            # n_comm_poll * navg_rt traces.

            start_time = time()
            prev_not_time = start_time

            for data in adc.fifo():
                a[:] = data[:, 0]
                calc_fft()
                calc_abs_square(y, b)
                # Now there is a new absolute squared FFT stored in y.

                # Adds the trace to the accumulator buffer, which is independent of the fast averaging.
                if navg_completed.value < navg.value:
                    if navg_completed.value == 0:
                        npbuff_acc[:] = y
                    else:
                        add_array(npbuff_acc, y)

                    navg_completed.value += 1

                i = (cnt.value % nbuff)   # The index inside the real-time buffer.

                if j == 0:
                    buff[i].acquire()
                    npbuff[i][:] = y
                else:
                    add_array(npbuff[i], y)

                j += 1

                if j == navg_rt:

                    # Updates the time domain data.
                    npbuff_t[i][:] = data[: nst, 0]

                    # Normalizes the spectrum to power spectral density. 
                    np.divide(npbuff[i], navg_rt * ns * sr, out=npbuff[i])

                    # Releases the lock so that the new spectrum and 
                    # the time domain data can be read by the ui process.
                    buff[i].release()

                    cnt.value += 1

                    j = 0  # Resets the fast averaging counter.

                    if cnt.value % n_comm_poll == 0:
                        now = time()
                        delay = (now - start_time) - navg_rt * cnt.value * dt_trace

                        if delay > 0 and (now - prev_not_time) > RT_NOT_INTVL:
                            # Prints how far it is from real-time prformance.
                            print(f"The data reading is behind real time by (s): {delay}")
                            prev_not_time = now

                        if conn.poll():
                            break


class RtsWindow(QtGui.QMainWindow):

    def __init__(self, card_args: Sequence = (), 
                 acq_settings: Union[dict, None] = None,
                 fft_lims: tuple = (12, 26)) -> None:
        super().__init__()

        defaults = {"mode": "fifo_single",
                    "channels": (0,),
                    "fullranges": (10,),
                    "terminations": ("1M",),
                    "samplerate": 30e6,
                    "nsamples": 2**19,
                    "trig_mode": "soft",
                    "navg_rt": 3}

        if acq_settings:
            defaults.update(acq_settings)

        self.setup_ui(card_args, defaults, fft_lims)

        self.card_args = card_args
        self.current_settings = defaults

        self.lbuff = 20  # The number of traces in the interprocess buffer.
        self.max_disp_samplerate = 1 * 10**7  # The maximum number of displayed
                                              # samples per second.
        self.max_disp_rate = 40  # The maximum number of plots per second.

        self.daq_proc = None  # A reference to the data acquisition process.

        # Shared variables for interprocess communication.
        self.navg = Value("i", 0, lock=False)
        self.navg_completed = Value("i", 0, lock=False)
        self.w_cnt = Value("i", 0, lock=False)

        self.pipe_conn = None

        self.r_cnt = 0

        self.buff = []  # List[Array]. The buffer for frequency-domain data.
        self.npbuff = []  # List[np.ndarray]. The same buffer as numpy arrays.

        self.buff_acc = None  # The buffer for averaged (accumulated) data.
        self.npbuff_acc = None

        self.buff_t = []  # List[Array]. The buffer for time-domain data.
        self.npbuff_t = []  # List[np.ndarray].

        self.show_overflow = True
        self.averging_now = False

        self.xfd = None
        self.yfd_ref = None
        self.xtd = None

        # Creates a timer that will start a data acquisition process once 
        # the Qt event loop is running.
        QtCore.QTimer.singleShot(100, self.update_daq) 

        # Starts a timer that will periodically update data displays.
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.timeout.connect(self.update_ui)
        self.updateTimer.start(0)

    def setup_ui(self, card_args, card_settings, fft_lims) -> None:
        """Sets up the user interface.
        """
        self.setWindowTitle("Spectrum Analyzer")
        self.resize(1500, 800)

        self.ui = RtsWidget()
        self.setStyleSheet(self.ui.styleSheet())  
        # Uses the widget stylesheet for the entire window.

        self.setCentralWidget(self.ui)

        self.ui.nsamplesComboBox.clear()
        for i in range(*fft_lims):
            self.ui.nsamplesComboBox.addItem(f"{2**i:,}", 2**i)

        with Card(*card_args) as adc:
            nchannels = adc._nchannels
            valid_fullranges_mv = adc._valid_fullranges_mv

        self.ui.channelComboBox.clear()
        for i in range(nchannels):
            self.ui.channelComboBox.addItem(str(i), i)

        self.ui.fullrangeComboBox.clear()
        for r in valid_fullranges_mv:
            self.ui.fullrangeComboBox.addItem("%g" % (r/1000), int(r)) 
            # The displayed fullranges are in Volts, but the item data is in mV 
            # to keep the values integer.

        self.card_fullranges_mv = [max(valid_fullranges_mv)] * nchannels 
        self.card_terminations = ["1M"] * nchannels
        # While for all other card settings the point of truth is the values of 
        # dedicated UI controls, the channel settings are stored in these
        # lists because only the parameters of one channel are displayed in UI
        # at a time.

        # Displays the current card settings.

        with NoSignals(self.ui.samplerateLineEdit) as uielem:
            uielem.setText("%i" % card_settings["samplerate"])

        with NoSignals(self.ui.nsamplesComboBox) as uielem:
            ind = uielem.findData(card_settings["nsamples"])
            uielem.setCurrentIndex(ind)

        with NoSignals(self.ui.navgrtLineEdit) as uielem:
            uielem.setText("%i" % card_settings["navg_rt"])

        ch = card_settings["channels"][0]

        with NoSignals(self.ui.channelComboBox) as uielem:
            uielem.setCurrentIndex(ch)

        with NoSignals(self.ui.fullrangeComboBox) as uielem:
            fr_mv = int(1000 * card_settings["fullranges"][0])  # Full range in mV.
            ind = uielem.findData(fr_mv) 
            uielem.setCurrentIndex(ind)
            self.card_fullranges_mv[ch] = fr_mv

        with NoSignals(self.ui.terminationComboBox) as uielem:
            term = card_settings["terminations"][0]
            ind = uielem.findData(term)
            uielem.setCurrentIndex(ind)
            self.card_terminations[ch] = term

        with NoSignals(self.ui.trigmodeComboBox) as uielem:
            ind = uielem.findData(card_settings["trig_mode"])
            uielem.setCurrentIndex(ind)

        # Connects the control panel.
        
        self.ui.channelComboBox.currentIndexChanged.connect(
            self.on_channel_change
        )
        self.ui.fullrangeComboBox.currentIndexChanged.connect(
            self.on_channel_param_change
        )
        self.ui.terminationComboBox.currentIndexChanged.connect(
            self.on_channel_param_change
        )

        self.ui.trigmodeComboBox.currentIndexChanged.connect(self.update_daq)

        self.ui.samplerateLineEdit.editingFinished.connect(self.update_daq)
        self.ui.nsamplesComboBox.currentIndexChanged.connect(self.update_daq)
        self.ui.navgrtLineEdit.editingFinished.connect(self.update_daq)

        self.ui.averagePushButton.clicked.connect(self.start_averaging)
        self.ui.naveragesLineEdit.editingFinished.connect(self.set_navg)
        self.ui.clearPushButton.clicked.connect(self.clear_ref)

        # Creates the plot lines.

        self.line = self.ui.spectrumPlot.plot()  # Real-time trace display.
        self.line.setPen((250, 0, 0))

        self.line_ref = self.ui.spectrumPlot.plot()  # Reference trace display.
        self.line_ref.setPen((20, 20, 20))

        self.line_td = self.ui.scopePlot.plot()  # Time domain display.
        self.line_td.setPen((126, 47, 142))

        # Setting x and y ranges removes autoadjustment.
        self.ui.spectrumPlot.setXRange(0, card_settings["samplerate"] / 2)
        self.ui.spectrumPlot.setYRange(-12, 1)

    def closeEvent(self, event):
        """Executed when the window is closed. This is an overloaded Qt method.
        """
        del event  # Unused but required by the signature.
        self.stop_daq()

    def update_ui(self):
        lbuff = len(self.buff)
        w_cnt = self.w_cnt.value  # The counter value of the writing process.

        if w_cnt > self.r_cnt and lbuff > 0:

            if w_cnt - self.r_cnt >= lbuff and self.show_overflow:
                print("Interprocess buffer overflow.")
                self.show_overflow = False

            i = self.r_cnt % lbuff

            self.buff[i].acquire()
            yfd = self.npbuff[i].copy()
            ytd = self.npbuff_t[i].copy()
            self.buff[i].release()

            self.r_cnt += 1

            # Updates the frequency domain display.
            self.line.setData(self.xfd, yfd)

            # Updates the time domain display.
            self.line_td.setData(self.xtd, ytd)

        if self.averging_now:
            navg_compl = self.navg_completed.value

            self.ui.averagesCompletedLabel.setText(str(navg_compl))

            if navg_compl >= self.navg.value:
                self.averging_now = False

                ns = self.current_settings["nsamples"]
                sr = self.current_settings["samplerate"]

                # Acquires and displays a new reference trace.
                self.yfd_ref = self.npbuff_acc / (navg_compl * ns * sr)
                self.line_ref.setData(self.xfd, self.yfd_ref)

    def update_daq(self) -> None:
        """Starts data acquisition in a separate process with present settings.
        """

        settings = self.get_settings_from_ui()

        if self.daq_proc and settings == self.current_settings:
            # Sometimes ui elements fire signals that call this function even
            # if there has been no actual change in the card settings.
            # Such calls are discarded.
            return

        self.r_cnt = 0
        self.show_overflow = True
        self.averging_now = False

        # Checks if there is a need to create a new process.
        new_proc = (not self.daq_proc or 
                    (settings["nsamples"] != self.current_settings["nsamples"]))

        if new_proc:

            if self.daq_proc and self.daq_proc.is_alive():
                self.stop_daq()

            # Before starting a new process, a buffer needs to be allocated for
            # interprocess communication, for which we need the number of samples. 
            # 2048 samples is the trace rounding margin.
            ns_est = settings["nsamples"] + 2048 
            nf_est = ns_est // 2 + 1  

            # Allocates bufferst that will be shared between the processes.
            # The frequency-domain buffers are completely responsible for synchronization, all other
            # shared buffers do not have their own locks.
            self.buff = [Array("d", nf_est, lock=True) for _ in range(self.lbuff)]
            self.buff_acc = Array("d", nf_est, lock=False)
            self.buff_t = [Array("d", ns_est // TDSF, lock=False) 
                           for _ in range(self.lbuff)]

            self.pipe_conn, conn2 = Pipe()

            self.daq_proc = Process(target=daq_loop,
                                    args=(self.card_args, conn2, 
                                          self.buff, self.buff_acc, self.buff_t, 
                                          self.w_cnt, self.navg, 
                                          self.navg_completed),
                                    daemon=True)
            self.daq_proc.start()

        if (settings["samplerate"] != self.current_settings["samplerate"] 
            or settings["nsamples"] != self.current_settings["nsamples"]):

            # Replace the current number of averages with a new estimate.
            settings["navg_rt"] = max(
                ceil(settings["samplerate"] / self.max_disp_samplerate),
                ceil((settings["samplerate"] / settings["nsamples"]) / self.max_disp_rate)
            )

        # Sends new settings.
        self.pipe_conn.send(settings)

        # Gets the true sampling rate and the trace size from the card.
        msg = self.pipe_conn.recv()

        sr = msg["samplerate"]
        ns = msg["nsamples"]

        settings.update(msg)
        self.current_settings = settings

        nf = ns // 2 + 1  # The number of frequency bins.
        nst = ns // TDSF  # The number of samples in the time-domain trace.

        if new_proc:
            # Formats the interprocess buffers based on the actual number of samples if a trace.
            self.npbuff = [np.ndarray((nf,), dtype=np.float64, buffer=a.get_obj())
                           for a in self.buff]
            self.npbuff_acc = np.ndarray((nf,), dtype=np.float64, 
                                         buffer=self.buff_acc)
            self.npbuff_t = [np.ndarray((nst,), dtype=np.float64, buffer=a) 
                            for a in self.buff_t]

        with NoSignals(self.ui.samplerateLineEdit) as uielem:
            uielem.setText("%i" % sr)
        with NoSignals(self.ui.nsamplesComboBox) as uielem:
            ind = uielem.findData(ns)
            uielem.setCurrentIndex(ind)
        with NoSignals(self.ui.navgrtLineEdit) as uielem:
            uielem.setText("%i" % settings["navg_rt"])

        # Displays the spacing between the Fourier transform frequencies.
        df = (sr / ns)
        self.ui.rbwLabel.setText("%.2f" % df)

         # Calculates the x axis and the spectrum plot.
        self.xfd = np.arange(0, nf) * df
        
        rng = settings["fullranges"][0] 
        self.xtd = np.linspace(0, nst / sr, nst)
        self.ui.scopePlot.setXRange(0, nst / sr)
        self.ui.scopePlot.setYRange(-rng, rng)

    def stop_daq(self) -> None:
        """Terminates the existing process."""

        if self.pipe_conn and self.daq_proc:
            self.pipe_conn.send("stop")
            self.daq_proc.join()

    def start_averaging(self):
        self.set_navg()
        self.averging_now = True

        # This tells the daq process to re-start averaging.
        self.navg_completed.value = 0

    def get_settings_from_ui(self) -> dict:
        """ Gets card settings from the user interface. 
        """

        # TODO: keep the total trace length above 10 us
        # Keep the total flux of points to display below 3 Ms/sec.

        trig_mode = self.ui.trigmodeComboBox.currentData()

        if trig_mode == "ext":
            card_mode = "fifo_multi"
        else:
            card_mode = "fifo_single"

        ch = self.ui.channelComboBox.currentData()
        frng = self.ui.fullrangeComboBox.currentData() / 1000  # The item data is in mV.
        term = self.ui.terminationComboBox.currentData()

        samplerate = int(float(self.ui.samplerateLineEdit.text()))
        nsamples = self.ui.nsamplesComboBox.currentData()
        navg_rt = int(float(self.ui.navgrtLineEdit.text()))

        # Copies the existing settings to preserve user-supplied values.
        new_settings = self.current_settings.copy()

        new_settings.update({"mode": card_mode,
                             "channels": (ch,),
                             "fullranges": (frng,),
                             "terminations": (term,),
                             "samplerate": samplerate,
                             "nsamples": nsamples,
                             "trig_mode": trig_mode,
                             "navg_rt": navg_rt})

        return new_settings

    def on_channel_change(self):
        ch = self.ui.channelComboBox.currentData()

        with NoSignals(self.ui.fullrangeComboBox) as uielem:
            ind = uielem.findData(self.card_fullranges_mv[ch])
            uielem.setCurrentIndex(ind)

        with NoSignals(self.ui.terminationComboBox) as uielem:
            ind = uielem.findData(self.card_terminations[ch])
            uielem.setCurrentIndex(ind)

        self.update_daq()

    def on_channel_param_change(self):
        ch = self.ui.channelComboBox.currentData()

        self.card_fullranges_mv[ch] = self.ui.fullrangeComboBox.currentData()
        self.card_terminations[ch] = self.ui.terminationComboBox.currentData()

        self.update_daq()

    def set_navg(self):
        self.navg.value = int(self.ui.naveragesLineEdit.text())

    def clear_ref(self):
        self.line_ref.setData([], [])


class RtsWidget(QtGui.QWidget, Ui_RtsWidget):
    """The widget that contains the user interface."""

    def __init__(self) -> None:
        super().__init__()
        self.setupUi(self)

        self.trigmodeComboBox.clear()
        self.trigmodeComboBox.addItem("Software", "soft")
        self.trigmodeComboBox.addItem("External", "ext")

        self.terminationComboBox.clear()
        self.terminationComboBox.addItem("1 MOhm", "1M")
        self.terminationComboBox.addItem("50 Ohm", "50")

        self.spectrumPlot.setBackground("w")
        self.spectrumPlot.setClipToView(True)
        self.spectrumPlot.setDownsampling(auto=True)  # If True, resample the data before plotting to avoid plotting multiple line segments per pixel.
        self.spectrumPlot.setLabel("left", "PSD", units="")
        self.spectrumPlot.setLabel("bottom", "Frequency", units="Hz")
        self.spectrumPlot.showAxis("right")
        self.spectrumPlot.showAxis("top")
        self.spectrumPlot.getAxis("top").setStyle(showValues=False)
        self.spectrumPlot.getAxis("right").setStyle(showValues=False)

        self.spectrumPlot.plotItem.setLogMode(False, True)  # Log y.
        self.spectrumPlot.plotItem.showGrid(True, True)

        self.scopePlot.setBackground("w")
        self.scopePlot.setLabel("left", "Signal", units="V")
        self.scopePlot.setLabel("bottom", "Time", units="s")
        self.scopePlot.showAxis("right")
        self.scopePlot.showAxis("top")
        self.scopePlot.getAxis("top").setStyle(showValues=False)
        self.scopePlot.getAxis("right").setStyle(showValues=False) 


def rts():
    """Starts a real-time spectrum analyzer."""

    # Same as app = QtGui.QApplication(*args) with optimum parameters
    app = mkQApp()

    mw = RtsWindow()
    mw.show()

    QtGui.QApplication.instance().exec_()


class NoSignals:
    """A context manager class that blocks signals from QObjects."""

    def __init__(self, uielement) -> None:
        self.uielement = uielement

    def __enter__(self):
        self.uielement.blockSignals(True)
        return self.uielement

    def __exit__(self, *a):
        self.uielement.blockSignals(False)


def add_array(a, b):
    """a = a + b 

    Adds two 1D arrays `b` and `a` element-wise and stores the result in `a`.
    """
    if a.shape[0] > 1e5:
        add_array_parallel(a, b)
    else:
        add_array_serial(a, b)


@njit
def add_array_serial(a, b):
    """The serial implementation of add_array."""
    for i in range(a.shape[0]):
        a[i] = a[i] + b[i]


@njit(parallel=True)
def add_array_parallel(a, b):
    """The parallel implementation of add_array."""
    for i in prange(a.shape[0]):
        a[i] = a[i] + b[i]


def calc_abs_square(a, b):
    """a = abs(b * b)

    Calculates absolute squares of the elements of a 1D array `b` and stores 
    the result in `a`.
    """
    if a.shape[0] > 1e5:
        calc_abs_square_parallel(a, b)
    else:
        calc_abs_square_serial(a, b)

@njit
def calc_abs_square_serial(a, b):
    """The serial implementation of calc_abs_square."""
    for i in range(a.shape[0]):
        a[i] = abs(b[i] * b[i])


@njit(parallel=True)
def calc_abs_square_parallel(a, b):
    """The parallel implementation of calc_abs_square."""
    for i in prange(a.shape[0]):
        a[i] = abs(b[i] * b[i])



if __name__ == '__main__':
    rts()
