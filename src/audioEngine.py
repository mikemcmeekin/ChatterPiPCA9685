# -*- coding: utf-8 -*-
"""
AudioEngine: plays wav tracks and drives the jaw (and eyes) from the
audio level, using the legacy STYLE 0/1/2 controllers.

Playback runs on a pump thread with a queue: at most one stream plays at
a time, so the jaw is always driven by exactly one audio callback.
All hardware writes go through the rig's worker thread.
"""
import atexit
import logging
import os
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
import soundfile as sf

import config as c
from bandpassFilter import BPFilter

log = logging.getLogger("chatterpi.audio")


class AudioEngine:
    def __init__(self, rig):
        c.update()
        self.rig = rig
        self.jaw = c.JAW_PART
        self.eyes = c.EYES_PART
        self.bp = BPFilter()
        spec = c.PARTS[self.jaw]
        # unflipped jaw range (direction flipping is applied at write time)
        self.j_min = min(spec['min_angle'], spec['max_angle'])
        self.j_max = max(spec['min_angle'], spec['max_angle'])
        self._queue = deque()
        self._stream = None
        self._finished = None
        self._closed = False
        self._pump = threading.Thread(target=self._pump, daemon=True)
        self._pump.start()
        atexit.register(self.close)

    # ---- public API ----

    def play_track(self, audio, block=False, drive=True):
        """Queue a track. `audio` is a file path or a filename in the
        vocals directory. `drive=False` plays the audio without driving
        the jaw (used for ambient tracks). Returns a threading.Event set
        when it finishes."""
        path = self.resolve(audio)
        ev = threading.Event()
        self._queue.append((path, ev, drive))
        if block:
            ev.wait()
        return ev

    def stop(self):
        """Stop the current track and drop everything queued."""
        while True:
            try:
                self._queue.popleft()
            except IndexError:
                break
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
        # guarantee the pump thread unblocks even if PortAudio does not
        # fire the finished callback for a manually stopped stream
        if self._finished is not None:
            self._finished.set()

    def is_playing(self):
        return self._stream is not None or len(self._queue) > 0

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.stop()

    # ---- internals ----

    def resolve(self, audio):
        """Resolve a track reference (path or vocals-dir filename) to a path."""
        if os.path.isabs(audio) or os.path.exists(audio):
            return audio
        return os.path.join(c.VOCALS_DIR, audio)

    def _pump(self):
        while True:
            try:
                path, ev, drive = self._queue.popleft()
            except IndexError:
                if self._closed:
                    return
                time.sleep(0.05)
                continue
            try:
                self._play_blocking(path, drive)
            except Exception as e:
                log.exception("playback of %s failed: %s", path, e)
            finally:
                ev.set()

    def _get_target(self, data, channels):
        """Map one audio block to a jaw target.

        `data` is float32 in [-1, 1] (what sounddevice/soundfile hand
        the callback). The config thresholds are on the legacy int16
        scale (the original code measured PyAudio int16 samples), so
        levels are scaled to that range before the style mapping.
        """
        def get_avg(levels):
            if c.STYLE == 2:
                levels = self.bp.filter_data(levels)
            levels = np.absolute(levels)
            if channels == 1:
                return levels.mean()
            # stereo: right channel only (legacy behaviour)
            return levels[:, 1].mean()

        volume = get_avg(data * 32767.0)
        jawStep = (self.j_max - self.j_min) / 3
        if c.STYLE == 0:
            jawTarget = self.j_max if volume > c.THRESHOLD else self.j_min
        elif c.STYLE == 1:
            if volume > c.LEVEL3:
                jawTarget = self.j_max
            elif volume > c.LEVEL2:
                jawTarget = self.j_min + 2 * jawStep
            elif volume > c.LEVEL1:
                jawTarget = self.j_min + jawStep
            else:
                jawTarget = self.j_min
        elif c.STYLE == 2:
            if volume > c.LEVEL3:
                jawTarget = self.j_max
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("max volume was reached %s", volume)
            elif volume > c.THRESHOLD:
                jawTarget = int((volume / c.LEVEL3) * self.j_max)
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("jawTarget %s vol %s lvl %s",
                              jawTarget, volume, c.LEVEL3)
            else:
                jawTarget = self.j_min
        else:
            if volume > c.FIlTERED_LEVEL3:
                jawTarget = self.j_max
            elif volume > c.FIlTERED_LEVEL2:
                jawTarget = self.j_min + 2 * jawStep
            elif volume > c.FIlTERED_LEVEL1:
                jawTarget = self.j_min + jawStep
            else:
                jawTarget = self.j_min
        return jawTarget

    def _play_blocking(self, path, drive=True):
        data, sr = sf.read(path, always_2d=True)
        channels = data.shape[1]
        if drive:
            self.bp.reset()

        current_frame = 0
        status_flag = False

        def filesCallback(outdata, frames, times, status):
            nonlocal current_frame, status_flag
            has_status = bool(status and str(status))
            if has_status != status_flag:
                status_flag = has_status
                if has_status:
                    log.warning("PortAudio status: %s", status)
                else:
                    log.info("PortAudio status cleared")
            chunksize = min(len(data) - current_frame, frames)
            if drive:
                # One jaw/eyes update per audio block (~11 ms at 44.1
                # kHz). This does numpy math and queue pushes only -
                # the actual I2C writes happen on the rig's worker
                # thread, so there is no buffer-overrun risk.
                jawTarget = self._get_target(
                    data[current_frame:current_frame + chunksize], channels)
                angle = 180 - jawTarget
                # raw (unsmoothed) writes: retargeting a smoothed part
                # every block would restart its ease each time and pile
                # up ~smoothing_ms of lag behind the audio
                self.rig.set_raw(self.jaw, angle)
                self.rig.set_raw(self.eyes, (jawTarget / 180) * 100)

            outdata[:chunksize] = data[current_frame:current_frame + chunksize]
            if chunksize < frames:
                outdata[chunksize:] = 0
                raise sd.CallbackStop()
            current_frame += chunksize

        finished = threading.Event()
        self._finished = finished
        stream = sd.OutputStream(samplerate=sr, channels=channels, blocksize=512,
                                 callback=filesCallback, finished_callback=finished.set,
                                 prime_output_buffers_using_stream_callback=True)
        self._stream = stream
        with stream:
            finished.wait()
        self._stream = None
        self._finished = None
        if drive:
            self.rig.set(self.jaw, c.PARTS[self.jaw]['rest'])