# -*- coding: utf-8 -*-
"""
Scripts: timed sequences of audio and part movements.

A script is a JSON file in the scripts directory:

    {
      "name": "greet",
      "steps": [
        {"t": 0.0, "audio": "v01.wav"},
        {"t": 0.4, "move": {"head": 15, "arm_l": 45, "ms": 300}},
        {"t": 3.5, "move": {"arm_l": 0, "ms": 400}},
        {"t": 4.0, "move": {"head": 0, "ms": 300}},
        {"t": 4.5, "set": {"eyes": 100}}
      ]
    }

`t` is the offset in seconds from the start of the script.
`audio`  - plays a track (jaw driven by the audio level automatically)
`move`   - moves the named parts to the given values over `ms` milliseconds
`set`    - sets the named parts immediately

All steps execute on a monotonic timeline anchored to a shared start time,
so several skeletons can play the same script locked together.
"""
import json
import logging
import os
import threading
import time

log = logging.getLogger("chatterpi.script")


class ScriptError(Exception):
    pass


class Script:
    def __init__(self, name, steps, directory=''):
        self.name = name
        self.directory = directory
        cleaned = []
        for step in steps:
            t = float(step.get('t', 0))
            if t < 0:
                raise ScriptError(f"step t must be >= 0, got {t}")
            if not any(k in step for k in ('audio', 'move', 'set')):
                raise ScriptError(f"step has no action at t={t}: {step}")
            cleaned.append((t, step))
        cleaned.sort(key=lambda x: x[0])
        self.steps = cleaned

    @classmethod
    def load(cls, name, directory):
        path = os.path.join(directory, name + '.json')
        if not os.path.isfile(path):
            raise ScriptError(f"script {name!r} not found in {directory}")
        with open(path) as f:
            data = json.load(f)
        if 'steps' not in data or not isinstance(data['steps'], list):
            raise ScriptError(f"script {name!r} must contain a 'steps' list")
        return cls(data.get('name', name), data['steps'], directory)

    @staticmethod
    def list_scripts(directory):
        if not os.path.isdir(directory):
            return []
        return sorted(f[:-5] for f in os.listdir(directory) if f.endswith('.json'))

    @property
    def duration(self):
        return self.steps[-1][0] if self.steps else 0.0


class ScriptPlayer:
    def __init__(self, rig, audio, directory, on_done=None):
        self.rig = rig
        self.audio = audio
        self.directory = directory
        self.on_done = on_done
        """Optional callback fired when a script finishes (naturally or
        via stop), letting the owner release any mode it held."""
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._current = None
        self.state = 'idle'

    def play(self, script_name, start_epoch=None, offset=0.0):
        """Schedule a script. start_epoch is the shared wall-clock time at
        which the script starts (e.g. supplied by the conductor); offset is
        this machine's clock offset relative to that shared clock.
        Returns a dict describing the schedule."""
        with self._lock:
            if self.state != 'idle':
                raise ScriptError(f"cannot play {script_name!r}: player is {self.state}")
            script = Script.load(script_name, self.directory)
            known = set(self.rig.parts)
            for t, step in script.steps:
                for key in ('move', 'set'):
                    if key in step:
                        for part in step[key]:
                            if part != 'ms' and part not in known:
                                log.warning("script %s references unknown part %r at t=%.2f",
                                            script.name, part, t)
                if 'audio' in step:
                    self.audio.resolve(step['audio'])
            if start_epoch is not None:
                local_start = float(start_epoch) + float(offset)
                target = time.monotonic() + (local_start - time.time())
            else:
                target = time.monotonic()
            self._current = script.name
            self.state = 'waiting' if target > time.monotonic() else 'playing'
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, args=(script, target),
                                            name='script-player', daemon=True)
            self._thread.start()
            return {'script': script.name, 'start_epoch': start_epoch, 'offset': offset,
                    'duration': script.duration}

    def stop(self):
        with self._lock:
            if self.state == 'idle':
                return
            self._stop_event.set()
            self.audio.stop()
        if self._thread is not None:
            self._thread.join(timeout=5)
        with self._lock:
            self.state = 'idle'
            self._current = None
        self.rig.rest_all()

    def status(self):
        with self._lock:
            return {'state': self.state, 'script': self._current}

    # ---- internals ----

    def _wait_until(self, deadline):
        while not self._stop_event.is_set():
            rem = deadline - time.monotonic()
            if rem <= 0:
                return
            if rem > 0.01:
                time.sleep(rem - 0.005)
            else:
                time.sleep(0.0002)

    def _run(self, script, t_start):
        audio_events = []
        try:
            if t_start > time.monotonic():
                self._wait_until(t_start)
            if self._stop_event.is_set():
                return
            self.state = 'playing'
            t0 = time.monotonic()
            for t, step in script.steps:
                if self._stop_event.is_set():
                    return
                self._wait_until(t0 + t)
                if self._stop_event.is_set():
                    return
                self._exec(step, audio_events)
            for ev in audio_events:
                while not ev.is_set() and not self._stop_event.is_set():
                    time.sleep(0.05)
            if not self._stop_event.is_set():
                self.rig.rest_all()
        except Exception:
            log.exception("script %s failed", script.name)
        finally:
            with self._lock:
                self.state = 'idle'
                self._current = None
            if self.on_done is not None:
                try:
                    self.on_done()
                except Exception:
                    log.exception("script on_done callback failed")

    def _exec(self, step, audio_events):
        if 'audio' in step:
            audio_events.append(self.audio.play_track(step['audio']))
        if 'move' in step:
            ms = int(step['move'].get('ms', 0))
            for part, value in step['move'].items():
                if part != 'ms':
                    self.rig.move(part, value, ms)
        if 'set' in step:
            for part, value in step['set'].items():
                self.rig.set(part, value)