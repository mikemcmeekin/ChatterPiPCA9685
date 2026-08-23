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
        def get_avg(levels):
            if c.STYLE == 2:
                levels = self.bp.filter_data(levels)
            levels = np.absolute(levels)
            if channels == 1:
                return np.sum(levels) // len(levels)
            right = levels[1::2]
            return np.sum(right) // len(right)

        levels = abs(np.frombuffer(data, dtype='<i2'))
        volume = get_avg(levels)
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

        current_frame = 0
        latest_time = time.monotonic()
        lastJawTarget = 0
        status_flag = False

        def filesCallback(outdata, frames, times, status):
            nonlocal latest_time, current_frame, lastJawTarget, status_flag
            has_status = bool(status and str(status))
            if has_status != status_flag:
                status_flag = has_status
                if has_status:
                    log.warning("PortAudio status: %s", status)
                else:
                    log.info("PortAudio status cleared")
            chunksize = min(len(data) - current_frame, frames)
            if drive:
                # Only process jaw movements every 0.3s, to avoid buffer overruns
                now = time.monotonic()
                if now - latest_time > 0.3:
                    latest_time = now
                    jawTarget = self._get_target(data[current_frame:current_frame + chunksize], channels)
                    angle = 180 - jawTarget
                    if abs(angle - lastJawTarget) < 6:
                        angle = int(angle * .8)
                    self.rig.set(self.jaw, angle)
                    lastJawTarget = angle
                    self.rig.set(self.eyes, (jawTarget / 180) * 100)

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