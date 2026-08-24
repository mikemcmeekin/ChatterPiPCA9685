# -*- coding: utf-8 -*-
"""
SkeletonCore: the single owner of one skeleton's hardware and playback.

Wires together the rig (all I2C output), the audio engine (tracks +
jaw driving), the script player (timed choreography) and the legacy
trigger/ambient control loop. Exposed to the world either through the
Viam module (skeletonModule.py) or directly in dev mode (main.py).
"""
import logging
import threading
import time

import config as c
from rig import SkeletonRig
from neck import Neck
from audioEngine import AudioEngine
from script import Script, ScriptPlayer, ScriptError
from tracks import Tracks
from control import run_control_loop

log = logging.getLogger("chatterpi.core")


class SkeletonCore:
    def __init__(self):
        c.update()
        self.rig = SkeletonRig()
        self.neck = self._build_neck()
        self.audio = AudioEngine(self.rig)
        self.player = ScriptPlayer(self.rig, self.audio, c.SCRIPTS_DIR,
                                   neck=self.neck,
                                   on_done=self._release_mode)
        self.tracks = Tracks(self.audio)
        self._lock = threading.Lock()
        self._legacy_thread = None
        self._legacy_stop = threading.Event()
        self.mode = 'idle'

    # ---- neck ----

    def _build_neck(self):
        """Create the two-servo neck from the [NECK] config, if any."""
        spec = c.NECK
        if spec is None:
            return None
        missing = [p for p in (spec['left_part'], spec['right_part'])
                   if p not in self.rig.parts]
        if missing:
            log.warning("neck configured but part(s) %s not in rig; neck disabled",
                        missing)
            return None
        return Neck(self.rig, spec)

    def neck(self, yaw=0.0, pitch=0.0, ms=400):
        """Turn the head: yaw -1 (left)..+1 (right), pitch -1 (down)..+1 (up)."""
        if self.neck is None:
            raise RuntimeError("neck not configured")
        self.neck.look(yaw, pitch, ms)

    def neck_preset(self, pose, ms=400):
        """Named neck pose: center / left / right / up / down."""
        if self.neck is None:
            raise RuntimeError("neck not configured")
        self.neck.look_preset(pose, ms)

    # ---- legacy trigger/ambient mode ----

    def start_legacy(self):
        with self._lock:
            if self.mode == 'idle':
                self.mode = 'legacy'
            else:
                log.warning("cannot start legacy control loop, mode is %s", self.mode)
                return
            self._legacy_stop.clear()
            self._legacy_thread = threading.Thread(target=run_control_loop,
                                                   args=(self, self._legacy_stop),
                                                   name='legacy-control', daemon=True)
            self._legacy_thread.start()

    # ---- script mode ----

    def play_script(self, script_name, start_epoch=None, offset=0.0):
        with self._lock:
            if self.mode == 'script':
                raise ScriptError("a script is already scheduled/playing")
            self.mode = 'script'
        try:
            result = self.player.play(script_name, start_epoch, offset)
        except Exception:
            self._release_mode()
            raise
        return result

    def stop(self):
        self.player.stop()
        self._release_mode()

    def _release_mode(self):
        with self._lock:
            if self.mode == 'script':
                self.mode = 'legacy' if self._legacy_thread is not None else 'idle'

    # ---- commands ----

    def get_time(self):
        """Current wall clock (epoch seconds) for conductor offset handshakes."""
        return {'epoch': time.time()}

    def list_scripts(self):
        return Script.list_scripts(c.SCRIPTS_DIR)

    def set_part(self, name, value, ms=0):
        if ms <= 0:
            self.rig.set(name, value)
        else:
            self.rig.move(name, value, ms)

    def rest_all(self):
        self.rig.rest_all()

    def status(self):
        with self._lock:
            mode = self.mode
        return {'mode': mode,
                'player': self.player.status(),
                'audio_playing': self.audio.is_playing(),
                'neck_ready': self.neck is not None,
                'parts': sorted(self.rig.parts)}

    # ---- lifecycle ----

    def close(self):
        self._legacy_stop.set()
        if self._legacy_thread is not None:
            self._legacy_thread.join(timeout=5)
        self.player.stop()
        self.audio.close()
        self.rig.close()