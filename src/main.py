#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dev entry point: runs SkeletonCore directly, without Viam.

Usage:
  python main.py                  # run the legacy trigger/ambient loop
  python main.py --script greet   # play one script, wait for it, exit
  python main.py --list-scripts   # list scripts and exit
"""
import argparse
import logging
import time

import config as c
c.update()

# invalid config check (can't have SOURCE == FILES and PROP_TRIGGER == START with legacy loop)
if c.SOURCE == "FILES" and c.PROP_TRIGGER == 'START' and c.AMBIENT == 'OFF':
    print("Note: SOURCE=FILES with PROP_TRIGGER=START plays once and exits.")

logging.basicConfig(level=logging.DEBUG if c.DEBUG else logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from script import Script
from skeleton import SkeletonCore


def main():
    parser = argparse.ArgumentParser(description="ChatterPi dev entry point (no Viam)")
    parser.add_argument("--script", help="play this script once and exit")
    parser.add_argument("--list-scripts", action="store_true", help="list scripts and exit")
    args = parser.parse_args()

    core = SkeletonCore()
    try:
        if args.list_scripts:
            print(Script.list_scripts(c.SCRIPTS_DIR))
            return
        if args.script:
            core.play_script(args.script)
            while core.player.status()["state"] != "idle":
                time.sleep(0.2)
            return
        core.start_legacy()
        try:
            while True:
                time.sleep(1)
                # START trigger runs once; exit when the legacy loop ends
                if core.mode == "idle" and c.PROP_TRIGGER == "START" and c.AMBIENT == "OFF":
                    break
        except KeyboardInterrupt:
            print("interrupted")
    finally:
        core.close()


if __name__ == "__main__":
    main()