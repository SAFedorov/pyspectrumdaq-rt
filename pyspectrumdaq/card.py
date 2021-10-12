from typing import Generator, Sequence

from ctypes import byref
from ctypes import c_void_p

import numpy as np
import numba

# Imports vendor-supplied driver functions
# ctype variables are named camelCase following the conventions of pyspcm.
from . import pyspcm as sp


class Card:
    """A class for communication with a Spectrum Instrumentation M-series data 
    acquisition cards."""

    def __init__(self, address: str = "/dev/spcm0"):
        """Connects to a DAQ card."""

        self._hCard = sp.spcm_hOpen(address)
        if not self._hCard:
            msg = ("The card could not be open. Try closing other software "
                   "that may be using it.")
            raise CardInaccessibleError(msg)

        # Reads the type, function and serial number of the card.
        card_type = self.get32(sp.SPC_PCITYP)
        serial_number = self.get32(sp.SPC_PCISERIALNO)
        func_type = self.get32(sp.SPC_FNCTYPE)

        # Translates the type to a readable name.
        card_name = szTypeToName(card_type)

        print(f"Card {card_name} SN {serial_number}.")

        # Checks that the card's type is analog input (AI).
        if func_type != sp.SPCM_TYPE_AI:
            self.close()
            msg = f"The card type ({func_type}) is not AI ({sp.SPCM_TYPE_AI})."
            raise CardIncompatibleError(msg)

        # Resets the card to prevent undefined behaviour.
        self.reset()

        # Reads the number of channels on the card.
        self._nchannels = (self.get32(sp.SPC_MIINST_MODULES)
                           * self.get32(sp.SPC_MIINST_CHPERMODULE))

        # Reads which channels are enabled.
        self._acq_channels = ()
        chan_mask = self.get32(sp.SPC_CHENABLE)
        for n in range(self._nchannels):
            if chan_mask & getattr(sp, "CHANNEL%i" % n):
                self._acq_channels += (n,)

        # Sampling rate in Hz.
        self._samplerate = self.get64(sp.SPC_SAMPLERATE)

        # The rest of the attributes are initialized with placeholder values.

        # The data acquisition mode (one of the std or fifo categories).
        # No mode have been configured yet.
        self._card_mode = None

        self._nsamples = 0  # The number of samples per channel per trace.

        self._pvBuffer = None  # A handle to a buffer for DMA data transfer.
        self._buffer = None    # A handle to the same buffer as a numpy array.
        self._nbufftraces = 0  # The size of the buffer in traces.
        self._trace_bsize = 0  # The size of each trace in bytes.

        # The factors for converting between ADC values and voltages
        # (for all channels, not the ones that are enabled).
        self._conversions = np.zeros(self._nchannels)

    def get32(self, reg: int) -> int:
        """Gets the value of a 32-bit register using spcm_dwGetParam_i32.
        Raises an exception if the spcm function returns a non-zero error code. 
        """
        dst = sp.int32(0)
        err = sp.spcm_dwGetParam_i32(self._hCard, reg, byref(dst))

        if err != sp.ERR_OK:
            raise RegisterAccessError(self.get_error_info())

        return dst.value

    def get64(self, reg: int) -> int:
        """Gets the value of a 64-bit register using spcm_dwGetParam_i64.
        Raises an exception if the spcm function returns a non-zero error code. 
        """
        dst = sp.int64(0)
        err = sp.spcm_dwGetParam_i64(self._hCard, reg, byref(dst))

        if err != sp.ERR_OK:
            raise RegisterAccessError(self.get_error_info())

        return dst.value

    def set32(self, reg: int, val: int):
        """Sets the value of a 32-bit register using spcm_dwSetParam_i32.
        Raises an exception if the spcm function returns a non-zero error code. 
        """
        err = sp.spcm_dwSetParam_i32(self._hCard, reg, val)

        if err != sp.ERR_OK:
            if err == sp.ERR_TIMEOUT:
                raise TimeoutError()
            else:
                raise RegisterAccessError(self.get_error_info())

    def set64(self, reg: int, val: int):
        """Sets the value of a 64-bit register using spcm_dwSetParam_i64.
        Raises an exception if the spcm function returns a non-zero error code. 
        """
        err = sp.spcm_dwSetParam_i64(self._hCard, reg, val)

        if err != sp.ERR_OK:
            if err == sp.ERR_TIMEOUT:
                raise TimeoutError()
            else:
                raise RegisterAccessError(self.get_error_info())

    def get_error_info(self) -> str:
        """Gets information on the last error that occurred.
        An alias for spcm_dwGetErrorInfo_i32.
        """
        szErrorBuff = sp.create_string_buffer(sp.ERRORTEXTLEN)
        sp.spcm_dwGetErrorInfo_i32(self._hCard, 0, 0, szErrorBuff)
        return szErrorBuff.value

    def close(self) -> None:
        """Closes the connection to the card."""
        sp.spcm_vClose(self._hCard)

    def reset(self) -> None:
        """Resets the card to default settings."""
        self.set32(sp.SPC_M2CMD, sp.M2CMD_CARD_RESET)

    def stop(self) -> None:
        """Stops any currently running data acquisition."""
        self.set32(sp.SPC_M2CMD, sp.M2CMD_CARD_STOP | sp.M2CMD_DATA_STOPDMA)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        """Closes the card connection and frees the memory buffer."""
        self.close()
        del self._pvBuffer
        del self._buffer

    def set_acquisition(self,
                        mode: str = "std_single",
                        channels: Sequence = (1,),
                        fullranges: Sequence = (10,),
                        terminations: Sequence = ("1M",),
                        samplerate: int = 30e6,
                        nsamples: int = 300e3,
                        timeout: float = 10,
                        pretrig_ratio: float = 0) -> None:
        """Sets acquisition parameters and initializes an appropriate buffer
        for data transfer.

        Args:
            mode: 
                The card mode. Can take one of the following values:
                'std_single'  - A single data segment is acquired for a single 
                trigger;
                'fifo_single' - The specified number (maybe infinite) of
                segments are acquired for a single trigger in a time-continuous 
                manner; 
                'fifo_multi'  - The specified number (maybe infinite) of 
                segments are acquired each after its own trigger event.
            channels:
                Specify channel number as e.g. 0, 1, 2 or 3.
            fullranges:
                The fullranges of channels in V. Have to be one of 
                {0.2, 0.5, 1, 2, 5, 10}.
            terminations:
                The channel terminations, can be '50' (50 Ohm) or '1M' (1 MOhm).
            samplerate: 
                The sample rate in Hz.
            nsamples:
                The number of samples per channel per data trace.
            timeout: 
                The timeout in s.
            pretrig_ratio:
                The fraction of samples in a trace that is recorded prior to 
                the trigger edge. 
        """

        nsamples = int(nsamples)
        samplerate = int(samplerate)
        mode = mode.lower()

        # Checks the consistency of input values.
        if nsamples % 4 != 0:
            nsamples = int(4 * round(nsamples / 4.))
            print(f"The number of samples was changed to {nsamples} because "
                  f"this number has to be divisible by 4.")

        if nsamples / samplerate > timeout:
            timeout = int(1.1 * nsamples / samplerate)
            print(f"The timeout is extended to {timeout} seconds to be greater "
                  f"than the acquisition time for a single trace.")

        # Enables and configures the specified channels and sets the card mode.
        self._set_channels(channels, terminations, fullranges)
        self._set_card_mode(mode)

        # Sets the sampling rate and reads it back, because the card can round 
        # this number without giving an error.
        self.set64(sp.SPC_SAMPLERATE, samplerate)
        self._samplerate = self.get64(sp.SPC_SAMPLERATE)

        # Setting the posttrigger value which has to be a multiple of 4.
        pretrig = np.clip(((nsamples*pretrig_ratio) // 4) * 4, 4, nsamples-4)
        self.set64(sp.SPC_POSTTRIGGER, nsamples - int(pretrig))

        # Sets the timeout value after converting it to milliseconds.
        self.set32(sp.SPC_TIMEOUT, int(timeout * 1e3))

        if mode == "std_single":

            # Sets the number of samples per channel to acquire in one run.
            self.set64(sp.SPC_MEMSIZE, nsamples)

            ntraces = 1  # A parameter for the memory buffer.

        elif mode == "fifo_single" or mode == "fifo_multi":

            # Sets the number of samples to acquire per channel per trace.
            self.set64(sp.SPC_SEGMENTSIZE, nsamples)

            # Configures the card for indefinite acquisition.
            self.set32(sp.SPC_LOOPS, 0)

            ntraces = 0  # A parameter for the memory buffer.

        self._nsamples = nsamples

        # Allocates a buffer and configures the data transfer.
        self._create_buffer(len(channels), nsamples, ntraces)

    def set_trigger(self, mode: str = "soft", channel: int = 0,
                    edge: str = "pos", level: float = 0) -> None:
        """Set triggering mode. Can be either "software", i.e. immediate 
        free-run, or on a rising or falling edge of one of the channels.

        Args:
            mode ('soft', 'ext' or 'chan'):
                Trigger mode, software, external or channel.
            channel:
                The channel number to trigger on. Only has an effect in
                channel mode, or, in the case of the card having more than one
                external trigger, in external mode.
            edge ('pos' or 'neg'):
                Trigger edge, positive or negative. Only has an effect in 
                channel or external trigger mode.
            level: 
                Trigger level in volts. Only has an effect in channel mode.
        """

        # Makes the arguments case-insensitive.
        mode = mode.lower()
        edge = edge.lower()

        if edge.startswith("pos"):
            edgespec = sp.SPC_TM_POS
        elif edge.startswith("neg"):
            edgespec = sp.SPC_TM_NEG
        else:
            raise ValueError("Incorrect trigger edge specification.")

        if mode.startswith("soft"):

            # Software trigger.

            self.set32(sp.SPC_TRIG_ANDMASK, 0)
            self.set32(sp.SPC_TRIG_ORMASK, sp.SPC_TMASK_SOFTWARE)
        elif mode.startswith("ext"):

            # External trigger.

            # Disables all other triggering.
            self.set32(sp.SPC_TRIG_ORMASK, 0)
            self.set32(sp.SPC_TRIG_CH_ORMASK0, 0)
            self.set32(sp.SPC_TRIG_CH_ORMASK1, 0)
            self.set32(sp.SPC_TRIG_CH_ANDMASK0, 0)
            self.set32(sp.SPC_TRIG_CH_ANDMASK1, 0)

            # Enables the external trigger.
            extmask = getattr(sp, "SPC_TMASK_EXT%i" % channel)
            self.set32(sp.SPC_TRIG_ANDMASK, extmask)

            trigreg = getattr(sp, "SPC_TRIG_EXT%i_MODE" % channel)
            self.set32(trigreg, edgespec)
        elif mode.startswith("chan"):

            # Channel level trigger.

            # Checks that the trigger level is within the channel full range.
            triglev = level / self._conversions[channel]
            maxadc = self.get32(sp.SPC_MIINST_MAXADCVALUE)
            if abs(triglev) >= maxadc:
                raise ValueError("The specified trigger level is outside "
                                 "the full range of the channel.")

            # Disables all other triggering
            self.set32(sp.SPC_TRIG_ORMASK, 0)
            self.set32(sp.SPC_TRIG_ANDMASK, 0)
            self.set32(sp.SPC_TRIG_CH_ORMASK1, 0)
            self.set32(sp.SPC_TRIG_CH_ANDMASK0, 0)
            self.set32(sp.SPC_TRIG_CH_ANDMASK1, 0)

            # Enables the required trigger.
            chmask = getattr(sp, "SPC_TMASK0_CH%i" % channel)
            self.set32(sp.SPC_TRIG_CH_ORMASK0, chmask)

            # Sets the trigger edge mode.
            trigreg = getattr(sp, "SPC_TRIG_CH%i_MODE" % channel)
            self.set32(trigreg, edgespec)

            # Finally, sets the trigger level.
            levelreg = getattr(sp, "SPC_TRIG_CH%i_LEVEL0" % channel)
            self.set32(levelreg, int(triglev / 4))
            # The division by 4 is necessary because the trigger has 14-bit
            # resolution while the card inputs have 16-bit resolution.
            # The two least significan bits of the card inputs are ignored.
        else:
            raise ValueError("Incorrect trigger mode.")

    def acquire(self, convert: bool = True) -> np.ndarray:
        """Acquires a trace without time axis. An appropriate buffer for
        data storage should be defined beforehand.

        Args:
            convert: 
                Specifies if the data should be converted to voltages (True) 
                or returned directly as ADC readings (False). ADC readings can 
                be scaled externally using the channel conversions.

        Returns:
            A (nsamples, nchanels) numpy array of float voltage samples  
            if `convert` is True or integer ADC samples if `convert` is False.
        """

        # Checks that the card is configured for a FIFO mode.
        if self._card_mode != "std_single":
            raise RuntimeError("The card has to be configured for std_single "
                               "mode.")

        # Defines DMA transfer with a notification when all data is received. 
        # This has to be done for every acquisition.
        err = sp.spcm_dwDefTransfer_i64(self._hCard, sp.SPCM_BUF_DATA,
                                        sp.SPCM_DIR_CARDTOPC, 0,
                                        self._pvBuffer, 0, self._trace_bsize)

        if err != sp.ERR_OK:
            raise CardError(self.get_error_info())

        # Starts the card and waits until the acquisition has finished.
        start_cmd = (sp.M2CMD_CARD_START | sp.M2CMD_CARD_ENABLETRIGGER
                     | sp.M2CMD_CARD_WAITREADY | sp.M2CMD_DATA_STARTDMA
                     | sp.M2CMD_DATA_WAITDMA)
        self.set32(sp.SPC_M2CMD, start_cmd)

        if convert:
            # Converts the data to voltage readings.
            cfs = tuple(self._conversions[n] for n in self._acq_channels)
            dim = (self._nsamples, len(self._acq_channels))
            data = np.zeros(dim, dtype=np.float64)
            _convert(data, self._buffer, cfs)
        else:
            # Takes a copy because the buffer can be overwritten by a next DMA.
            data = self._buffer.copy()

        return data

    def fifo(self, convert: bool = True) -> Generator:
        """Acquires one trace without time axis in FIFO mode.

        Args:
            convert:
                Specifies if the data should be converted to voltages (True) 
                or returned directly as ADC readings (False). ADC readings can 
                be scaled externally using the channel conversions.

        Yields:
            A (nsamples, nchanels) numpy array of float voltage samples  
            if `convert` is True or integer ADC samples if `convert` is False.
        """

        # Checks that the card is configured for a FIFO mode.
        if self._card_mode not in ("fifo_single", "fifo_multi"):
            raise RuntimeError("The card has to be configured for fifo_single "
                               "or fifo_multi mode.")

        # Defines data transfer with a notification for every new trace.
        buff_size = self._nbufftraces * self._trace_bsize
        notify_size = self._trace_bsize
        err = sp.spcm_dwDefTransfer_i64(self._hCard, sp.SPCM_BUF_DATA,
                                        sp.SPCM_DIR_CARDTOPC, notify_size,
                                        self._pvBuffer, 0, buff_size)

        if err != sp.ERR_OK:
            raise CardError(self.get_error_info())

        # Shorthand notations.
        ns = self._nsamples
        nchannels = len(self._acq_channels)
        cfs = tuple(self._conversions[n] for n in self._acq_channels)

        i = 0  # Initializes the buffer segment counter.

        # Starts the card, enables the trigger, starts data transfer 
        # and waits for the first segment of data to arrive.
        start_cmd = (sp.M2CMD_CARD_START | sp.M2CMD_CARD_ENABLETRIGGER
                     | sp.M2CMD_DATA_STARTDMA | sp.M2CMD_DATA_WAITDMA)
        self.set32(sp.SPC_M2CMD, start_cmd)

        while True:
            if convert:
                # Converts the data to voltage readings.
                data = np.zeros((ns, nchannels), dtype=np.float64)
                _convert(data, self._buffer[i * ns: (i + 1) * ns, :], cfs)
            else:
                # Takes a copy because the buffer can be overwritten.
                data = self._buffer[i * ns: (i + 1) * ns, :].copy()

            # Notifies that some space in the buffer is free for writing again.
            self.set64(sp.SPC_DATA_AVAIL_CARD_LEN, self._trace_bsize)

            yield data

            # Waits for a new segment of data in the buffer.
            self.set32(sp.SPC_M2CMD, sp.M2CMD_DATA_WAITDMA)

            # Increments the segment counter in a circular manner.
            i += 1
            if i >= self._nbufftraces:
                i = 0

    def set_clock(self, mode: str = "int", ext_freq: int = 10000000) -> None:
        """Sets the clock mode, which can be internal ('int') or 
        external ('ext'). For external mode, an external clock frequency 
        must be specified (in Hertz).
        """

        mode = mode.lower()  # The argument is case-insensitive.

        if mode.startswith("int"):
            self.set32(sp.SPC_CLOCKMODE, sp.SPC_CM_INTPLL)  # Internal clock.
        elif mode.startswith("ext"):
            # Sets the clock to external reference.
            self.set32(sp.SPC_REFERENCECLOCK, int(ext_freq))
            self.set32(sp.SPC_CLOCKMODE, sp.SPC_CM_EXTREFCLOCK)
        else:
            raise ValueError(f"The clock mode must be 'int' or 'ext', "
                             f"not {mode!r}")

    @property
    def samplerate(self):
        """The sampling rate of input readings."""
        return self._samplerate

    @samplerate.setter
    def samplerate(self, val):
        raise TypeError("The sample rate should be set using set_acquisition.")

    def _set_card_mode(self, mode: str) -> None:
        """Sets the card mode. The valid values are:

        'std_single', 'std_multi', 'std_gate', 'std_aba',
        'fifo_single', 'fifo_multi', 'fifo_gate', 'fifo_aba'

        The argument is case-insensitive.
        """

        # Checks the consistency of the argument value.
        mode = mode.lower()
        valid_modes = ['std_single', 'std_multi', 'std_gate', 'std_aba',
                       'fifo_single', 'fifo_multi', 'fifo_gate', 'fifo_aba']
        if mode not in valid_modes:
            raise ValueError(f"The mode must be one of the "
                             f"following: {valid_modes}, not {mode!r}.")

        # Sets the card mode.
        mode_val = getattr(sp, "SPC_REC_%s" % mode.upper())
        self.set32(sp.SPC_CARDMODE, mode_val)
        self._card_mode = mode

    def _set_channels(self,
                      channels: Sequence = (1,),
                      terminations: Sequence = ("1M",),
                      fullranges=(10,)) -> None:
        """Enables and configures input channels. The argument lists have 
        to be of the same length.

        Args:
            channels: 
                A list of channels to enable addressed by their numbers.
            terminations: 
                A list of terminations to use with these channels. Each 
                termination can be '1M' to set it to high impedance, or '50'
                to set it to 50 Ohm.
            fullranges: 
                A list of ranges in volts for these channels.
        """

        if len(channels) not in [1, 2, 4, 8, 16]:
            raise ValueError("The number of activated channels has to be 2^n.")

        if not all((n in range(self._nchannels)) for n in channels):
            raise ValueError("Some channel numbers are invalid")

        # Sort all the arrays.
        sort_idx = np.argsort(channels)
        acq_channels = np.array(channels)[sort_idx]
        terminations = np.array(terminations)[sort_idx]
        fullranges = np.array(fullranges)[sort_idx]

        # Enables the channels by creating a CHENABLE mask and applying it
        chan_mask = 0

        for ch_n in channels:
            chan_mask |= getattr(sp, "CHANNEL%i" % ch_n)

        self.set32(sp.SPC_CHENABLE, chan_mask)
        self._acq_channels = acq_channels

        maxadc = self.get32(sp.SPC_MIINST_MAXADCVALUE)

        for ch_n, term, fullrng in zip(channels, terminations, fullranges):
            fullrng = int(fullrng * 1000)

            if fullrng in [200, 500, 1000, 2000, 5000, 10000]:
                range_reg = getattr(sp, "SPC_AMP%i" % ch_n)
                self.set32(range_reg, fullrng)

                conversion = float(fullrng) / 1000 / maxadc
                self._conversions[ch_n] = conversion
            else:
                raise ValueError("The specified voltage range is invalid.")

            if term == "1M":
                term_val = 0
            elif term == "50":
                term_val = 1
            else:
                raise ValueError("The specified termination is invalid")

            term_param = getattr(sp, "SPC_50OHM%i" % ch_n)
            self.set32(term_param, term_val)

    def _create_buffer(self, nchannels: int, nsamples: int, 
                       ntraces: int) -> None:
        """Allocates a buffer for data transfer. The buffer size is always equal
        to the size of an integer number of traces, which is smaller or equal 
        to `ntraces`. 

        Uses a continuous memory buffer if it is available and can accomodate 
        at least one trace. In this case the buffer size is also rounded to 
        an integer number of traces.

        The notification size is always set to the size of one trace.

        Args:
            nchannels: 
                The number of acquisition channels.
            nsamples:
                The number of samples per trace per channel.
            ntraces: 
                The number of traces to acquire in total. If set to zero, this 
                corresponds to an infinite number of traces. 
        """

        bps = self.get32(sp.SPC_MIINST_BYTESPERSAMPLE)  # Bytes per sample.
        trace_bsize = bps*nsamples*nchannels  # The size of one trace in bytes.

        # Tries getting a continuous buffer. This is only expected to work
        # if an external pre-setup has been done as described in the manual.
        self._pvBuffer = c_void_p()
        qwContBufLen = sp.uint64(0)
        err = sp.spcm_dwGetContBuf_i64(self._hCard, sp.SPCM_BUF_DATA,
                                       byref(self._pvBuffer),
                                       byref(qwContBufLen))

        if err != sp.ERR_OK:
            raise CardError(self.get_error_info())

        if qwContBufLen.value >= trace_bsize:
            print("Using a continuous buffer.")

            # Rounds the size of the received buffer to an integer
            # number of traces.
            nbufftraces = qwContBufLen.value // trace_bsize
        else:
            # Creates a regular buffer.

            # Reads the card memory size in bytes.
            card_mem_lim = self.get64(sp.SPC_PCIMEMSIZE)

            if ntraces == 0 or (ntraces * trace_bsize) > card_mem_lim:
                nbufftraces = max((card_mem_lim // trace_bsize), 1)

                # In this case, the acquisition proceeds indefinitely or
                # the total size of acquired traces is larger than the card
                # memory size. Both situations are fine in FIFO modes.
                # On the card side, all its memory can be used as a buffer.
                # We allocate a buffer of the same size (modulo the trace size)
                # on the computer.
            else:
                nbufftraces = ntraces

            self._pvBuffer = sp.create_string_buffer(trace_bsize * nbufftraces)
            print("Using a regular buffer.")

        self._nbufftraces = nbufftraces
        self._trace_bsize = trace_bsize

        # For the convenience of access, we also represent the allocated buffer
        # as a 2D numpy array of 16 bit integers.
        arr = np.frombuffer(self._pvBuffer, dtype=np.int16)
        self._buffer = np.reshape(arr, (nbufftraces * nsamples, nchannels))

        # Another way of recasting the buffer is given below. It works, but 
        # causes memory leak: after del self._buffer and del self._pvBuffer, 
        # the memory they point to is not freed. Apparently, ctypes.cast is
        # the culprit, see https://stackoverflow.com/questions/61479041/ctypes-does-not-free-string-buffers
        #
        # pnData = cast(self._pvBuffer, sp.ptr16)
        # dim = (nbufftraces * nsamples, nchannels)
        # self._buffer = np.ctypeslib.as_array(pnData, shape=dim)


class CardError(Exception):
    """The base class for card errors."""
    pass


class CardInaccessibleError(CardError):
    pass


class CardIncompatibleError(CardError):
    pass


class RegisterAccessError(CardError):
    """The class for errors that happened during set/get operations performed
    on the card registers."""
    pass


class TimeoutError(CardError):
    """The error raised when a timeout occurred while waiting for 
    a driver response."""
    pass


def szTypeToName(lCardType: int) -> str:
    """A vendor-supplied function for card name translation."""

    lVersion = (lCardType & sp.TYP_VERSIONMASK)
    lType = (lCardType & sp.TYP_SERIESMASK)

    if lType == sp.TYP_M2ISERIES:
        name = 'M2i.%04x' % lVersion
    elif lType == sp.TYP_M2IEXPSERIES:
        name = 'M2i.%04x-Exp' % lVersion
    elif lType == sp.TYP_M3ISERIES:
        name = 'M3i.%04x' % lVersion
    elif lType == sp.TYP_M3IEXPSERIES:
        name = 'M3i.%04x-Exp' % lVersion
    elif lType == sp.TYP_M4IEXPSERIES:
        name = 'M4i.%04x-x8' % lVersion
    elif lType == sp.TYP_M4XEXPSERIES:
        name = 'M4x.%04x-x4' % lVersion
    else:
        name = ''

    return name


@numba.jit(nopython=True, parallel=True)
def _convert(dst, src, scalefs):
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