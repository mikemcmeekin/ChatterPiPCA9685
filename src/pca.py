# -*- coding: utf-8 -*-
"""
Single shared PCA9685 driver.

All servo and LED code must use get_pca() instead of opening its own
PCA9685, so the chip is initialized exactly once and every component
agrees on the PWM frequency.

NOTE - non-standard I2C access (verified on this board with controlled
write/read tests, i2c_exp): the PCA9685 here is a clone whose I2C
interface does NOT auto-increment the register pointer:
  * every byte of a multi-byte WRITE lands in the pointer register
    itself (last byte wins) - a 4-byte channel write only touches the
    ON_L register, leaving the pulse-width (OFF) registers frozen;
  * the 2nd byte of a 2-byte READ repeats the 1st.
Single-byte [pointer, value] writes and 1-byte reads land correctly,
so all channel access goes through _SingleBytePWMRegs, which the
driver's channel objects use via pca.pwm_regs.
"""
import logging
import threading
import time

import board
from adafruit_pca9685 import PCA9685

log = logging.getLogger("chatterpi.pca")

_pca = None
_pca_lock = threading.Lock()


class _SingleBytePWMRegs:
    """Channel register access via single-byte I2C ops only (see module
    docstring). Implements the driver's pwm_regs interface:
    element i == (on_u16, off_u16) for channel i."""

    _BASE = 0x06
    _COUNT = 16

    def __init__(self, i2c, address=0x40):
        self._i2c = i2c
        self._addr = address

    def _write_reg(self, reg, value):
        self._i2c.writeto(self._addr, bytes([reg, value & 0xFF]))

    def _read_reg(self, reg):
        b = bytearray(1)
        self._i2c.writeto_then_readfrom(self._addr, bytes([reg]), b)
        return b[0]

    def __getitem__(self, index):
        base = self._BASE + 4 * index
        on = self._read_reg(base) | (self._read_reg(base + 1) << 8)
        off = self._read_reg(base + 2) | (self._read_reg(base + 3) << 8)
        return on, off

    def __setitem__(self, index, value):
        on, off = value
        base = self._BASE + 4 * index
        self._write_reg(base, on & 0xFF)
        self._write_reg(base + 1, (on >> 8) & 0xFF)
        self._write_reg(base + 2, off & 0xFF)
        self._write_reg(base + 3, (off >> 8) & 0xFF)


def _wake(pca, delay=0.0):
    """Clear the MODE1 sleep bit after `delay` seconds.

    Defensive: a previous driver's teardown could leave a genuine
    PCA9685 in sleep (MODE1=0x20, outputs disabled) after we init it.
    On the opgrimbw clone the MODE1 register reads 0x00 and does not
    hold writes, so this is a no-op here."""
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
            i2c = board.I2C()
            _pca = PCA9685(i2c)
            _pca.pwm_regs = _SingleBytePWMRegs(i2c)
            _wake(_pca)                       # wake now...
            _pca.frequency = frequency
            _wake(_pca, delay=3.0)            # ...and again once any
            # dying old driver is guaranteed to be gone
    return _pca