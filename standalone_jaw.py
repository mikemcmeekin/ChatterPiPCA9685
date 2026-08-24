"""Standalone jaw drive test: real rig + real audio engine, no Viam.
Sample the jaw pulse (OFF_L=0x08) and eyes (OFF_L=0x18) registers
while v01.wav plays. Run with viam-agent stopped (module owns the chip)."""
import sys
import threading
import time

sys.path.insert(0, "/root/ChatterPi/src")
import os
os.chdir("/root/ChatterPi/src")
os.environ["CHATTERPI_CONFIG"] = "/root/ChatterPi/src/config.ini"

import numpy as np
import soundfile as sf

import board
import config as c
c.update()
from rig import SkeletonRig
from audioEngine import AudioEngine

i2c = board.I2C()


def rd(reg):
    b = bytearray(1)
    i2c.writeto_then_readfrom(0x40, bytes([reg]), b)
    return b[0]


rig = SkeletonRig()
audio = AudioEngine(rig)

rows = []
stop = threading.Event()


def sampler():
    while not stop.is_set():
        rows.append((time.monotonic(), rd(0x08), rd(0x09), rd(0x18)))
        time.sleep(0.05)


t0 = time.monotonic()
s = threading.Thread(target=sampler, daemon=True)
s.start()
print("playing v01.wav (22 s)...", flush=True)
audio.play_track("v01.wav", block=True)
stop.set()
s.join(timeout=2)
audio.close()
rig.close()

# analysis: jaw pulse = (OFF_L | OFF_H<<8) * 16 duty -> pulse width us
jaw = [((r[1] | r[2] << 8)) * 16 for r in rows]
eyes = [r[3] for r in rows]
ts = [r[0] - t0 for r in rows]

# envelope of the wav for reference
wav, sr = sf.read("/root/ChatterPi/src/vocals/v01.wav", always_2d=True)
env_win = 512
n = len(wav) // env_win
env = np.abs(wav[:n * env_win].reshape(n, env_win, 1)).mean(axis=(1, 2)) * 32767
env_t = ((np.arange(n) + 0.5) * env_win) / sr

grid = np.arange(0, len(ts), 1)
jaw_a = np.array(jaw, dtype=float)
a = (env - env.mean()) / (env.std() + 1e-9)
b = (jaw_a - jaw_a.mean()) / (jaw_a.std() + 1e-9)
# jaw PULSE is HIGH when jaw is CLOSED (silence) -> invert for correlation
b = -b
corr = np.correlate(b, a, mode="full")
lags = (np.arange(len(corr)) - (len(a) - 1)) / sr
peak = lags[int(np.argmax(corr))]

print(f"jaw pulse: rest~{np.median(jaw[:40]):.0f} duty, "
      f"min={jaw_a.min():.0f} max={jaw_a.max():.0f} duty "
      f"({jaw_a.min()/65535*16.67:.0f}us..{jaw_a.max()/65535*16.67:.0f}us)")
print(f"eyes OFF_L: min={min(eyes)} max={max(eyes)} (0=off, varies=bright with audio)")
print(f"jaw pulse tracks audio: LAG {peak*1000:+.0f} ms (corr={corr.max()/len(a):.3f})")
# show a few moments
print("t(s)   jaw_duty  eyes  env")
for i in range(0, len(ts), 10):
    print(f"{ts[i]:5.1f} {jaw[i]:8.0f} {eyes[i]:5d} {env[int(min(i/len(ts)*n, n-1))]:6.0f}")