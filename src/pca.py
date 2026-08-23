# -*- coding: utf-8 -*-
"""
Single shared PCA9685 driver.

All servo and LED code must use get_pca() instead of opening its own
PCA9685, so the chip is initialized exactly once and every component
agrees on the PWM frequency.
"""
import logging
import threading
import time

import board
from adafruit_pca9685 import PCA9685

log = logging.getLogger("chatterpi.pca")

_pca = None
_pca_lock = threading.Lock()


def _wake(pca, delay=0.0):
    """Clear the MODE1 sleep bit after `delay` seconds.

    Another driver's teardown (e.g. a viam-labs PCA9685 module being
    replaced) can write MODE1=0x20 (sleep - all outputs disabled) a
    moment AFTER we initialize the chip. The driver's frequency setter
    preserves whatever MODE1 it finds, so the sleep would otherwise
    stick forever and the servos would silently stop moving."""
    def _do():
        time.sleep(delay)
        try:
            mode = pca.mode1_reg
            if mode & 0x20:
                log.warning("PCA9685 is in sleep mode (MODE1=0x%02x); waking", mode)
                pca.mode1_reg = mode & ~0x20
        except Exception as e:
            log.warning("PCA9685 wake failed: %s", e)
    threading.Thread(target=_do, daemon=True, name="pca-wake").start()


def get_pca(frequency=60):
    global _pca
    with _pca_lock:
        if _pca is None:
            _pca = PCA9685(board.I2C())
            _wake(_pca)                       # wake now...
            _pca.frequency = frequency
            _wake(_pca, delay=3.0)            # ...and again once any
            # dying old driver is guaranteed to be gone
    return _pca