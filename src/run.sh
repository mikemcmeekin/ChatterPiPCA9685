#!/bin/sh
# Viam module entrypoint. Runs from the src directory so relative paths
# (scripts/, config.ini defaults) resolve the same way as in dev mode.
cd /root/ChatterPi/src
exec /root/ChatterPi/venv/bin/python3 skeletonModule.py "$@"
