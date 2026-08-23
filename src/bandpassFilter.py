#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri May 15 16:44:44 2020

@author: Mike McGurrin

Voice-band (500-2500 Hz) band-pass for volume analysis.

The legacy version restarted lfilter on every audio block with no
carried state, so the 6th-order filter never reached steady state and
the volume estimate was unstable. State is now carried across blocks
and reset at the start of each track.
"""
import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi

class BPFilter:
    FS = 44100.0      # filter design rate (tracks are 44.1 kHz)
    LOWCUT = 500.0
    HIGHCUT = 2500.0
    ORDER = 6

    def __init__(self):
        self._b = None
        self._a = None
        self._zi = None    # list of per-channel filter states (or 1-D for mono)

    def reset(self):
        """Drop filter state - call when a new track starts."""
        self._zi = None

    def _design(self):
        nyq = 0.5 * self.FS
        self._b, self._a = butter(self.ORDER,
                                  [self.LOWCUT / nyq, self.HIGHCUT / nyq],
                                  btype='band')

    def filter_data(self, data):
        if self._b is None:
            self._design()
        data = np.asarray(data)
        if data.ndim == 2:
            if self._zi is None:
                self._zi = [lfilter_zi(self._b, self._a)
                            for _ in range(data.shape[1])]
            out = np.empty_like(data)
            for ch in range(data.shape[1]):
                y, self._zi[ch] = lfilter(self._b, self._a, data[:, ch],
                                          zi=self._zi[ch])
                out[:, ch] = y
            return out
        if self._zi is None:
            self._zi = lfilter_zi(self._b, self._a)
        y, self._zi = lfilter(self._b, self._a, data, zi=self._zi)
        return y