#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 18 2020

@author: Mike McGurrin

Configuration is read from config.ini. Each physical piece of hardware
(servo or LED) is described by a [PART <name>] section, so every skeleton
can declare its own equipment in its own config file:

    [PART jaw]
    type = servo
    channel = 0
    min_angle = 20
    max_angle = 180
    pulse_min = 600
    pulse_max = 2400
    rest = 20

    [PART eyes]
    type = led
    channel = 4

Legacy configs without [PART] sections still work: parts are synthesized
from the old [SERVO] / [PINS] sections.
"""
from configparser import ConfigParser
import os

cfg = ConfigParser()
CONFIG_PATH = os.environ.get('CHATTERPI_CONFIG', '/root/ChatterPi/src/config.ini')

def update():
	global cfg
	global SERVO_MIN
	global SERVO_MAX
	global MIN_ANGLE
	global MAX_ANGLE
	global STYLE
	global THRESHOLD
	global LEVEL1
	global LEVEL2
	global LEVEL3
	global FIlTERED_LEVEL1
	global FIlTERED_LEVEL2
	global FIlTERED_LEVEL3
	global BUFFER_SIZE
	global SOURCE
	global MIC_TIME
	global OUTPUT_CHANNELS
	global AMBIENT
	global PROP_TRIGGER
	global EYES
	global TRIGGER_OUT
	global DELAY
	global JAW_PIN
	global PIR_PIN
	global EYES_PIN
	global TRIGGER_OUT_PIN
	global DEBUG
	global SCRIPTS_DIR
	global VOCALS_DIR
	global AMBIENT_DIR
	global JAW_PART
	global EYES_PART
	global TRIGGER_OUT_PART
	global PARTS

	# Fresh parser each update so removed/renamed sections don't survive
	# a re-read (the control panel rewrites config.ini while running).
	cfg = ConfigParser()
	cfg.read(CONFIG_PATH)

	SERVO_MIN = int(cfg['SERVO']['SERVO_MIN'])
	SERVO_MAX = int(cfg['SERVO']['SERVO_MAX'])
	MIN_ANGLE = int(cfg['SERVO']['MIN_ANGLE'])
	MAX_ANGLE = int(cfg['SERVO']['MAX_ANGLE'])
	STYLE = int(cfg['CONTROLLER']['STYLE'])
	THRESHOLD = int(cfg['CONTROLLER']['THRESHOLD'])
	LEVEL1 = int(cfg['CONTROLLER']['LEVEL1'])
	LEVEL2 = int(cfg['CONTROLLER']['LEVEL2'])
	LEVEL3 = int(cfg['CONTROLLER']['LEVEL3'])
	FIlTERED_LEVEL1 = int(cfg['CONTROLLER']['FIlTERED_LEVEL1'])
	FIlTERED_LEVEL2 = int(cfg['CONTROLLER']['FIlTERED_LEVEL2'])
	FIlTERED_LEVEL3 = int(cfg['CONTROLLER']['FIlTERED_LEVEL3'])
	DEBUG = cfg['CONTROLLER'].getboolean('debug', fallback=False)
	BUFFER_SIZE = int(cfg['AUDIO']['BUFFER_SIZE'])
	SOURCE = cfg['AUDIO']['SOURCE']
	MIC_TIME = int(cfg['AUDIO']['MIC_TIME'])
	OUTPUT_CHANNELS = cfg['AUDIO']['OUTPUT_CHANNELS']
	AMBIENT = cfg['AUDIO']['AMBIENT']
	JAW_PART = cfg.get('AUDIO', 'jaw_part', fallback='jaw')
	PROP_TRIGGER = cfg['PROP']['PROP_TRIGGER']
	EYES = cfg['PROP']['EYES']
	TRIGGER_OUT = cfg['PROP']['TRIGGER_OUT']
	DELAY = int(cfg['PROP']['DELAY'])
	JAW_PIN = int(cfg['PINS']['JAW_PIN'])
	PIR_PIN = int(cfg['PINS']['PIR_PIN'])
	EYES_PIN = int(cfg['PINS']['EYES_PIN'])
	TRIGGER_OUT_PIN = int(cfg['PINS']['TRIGGER_OUT_PIN'])
	SCRIPTS_DIR = cfg.get('SCRIPTS', 'directory', fallback='scripts')
	VOCALS_DIR = cfg.get('AUDIO', 'vocals_dir', fallback='/root/ChatterPi/src/vocals/')
	AMBIENT_DIR = cfg.get('AUDIO', 'ambient_dir', fallback='/root/ChatterPi/src/ambient/')
	EYES_PART = cfg.get('PROP', 'eyes_part', fallback='eyes')
	TRIGGER_OUT_PART = cfg.get('PROP', 'trigger_out_part', fallback='trigger_out')

	# Collect explicit [PART <name>] sections
	PARTS = {}
	for section in cfg.sections():
		if section.lower().startswith('part '):
			name = section[5:].strip()
			spec = {key: value for key, value in cfg.items(section)}
			spec['type'] = spec.get('type', 'servo').lower()
			spec['channel'] = int(spec.get('channel', 0))
			spec['enabled'] = cfg.getboolean(section, 'enabled', fallback=True)
			if spec['type'] == 'servo':
				spec['min_angle'] = float(spec.get('min_angle', MIN_ANGLE))
				spec['max_angle'] = float(spec.get('max_angle', MAX_ANGLE))
				spec['pulse_min'] = int(spec.get('pulse_min', SERVO_MIN))
				spec['pulse_max'] = int(spec.get('pulse_max', SERVO_MAX))
				spec['rest'] = float(spec.get('rest', spec['min_angle']))
			elif spec['type'] == 'led':
				spec['min_brightness'] = float(spec.get('min_brightness', 0))
				spec['max_brightness'] = float(spec.get('max_brightness', 100))
				spec['rest'] = float(spec.get('rest', spec['min_brightness']))
			else:
				raise ValueError(f"Unknown part type {spec['type']} for part {name}")
			PARTS[name] = spec

	# Legacy fallback: synthesize parts from old [SERVO]/[PINS] sections
	if 'jaw' not in PARTS:
		PARTS['jaw'] = {'type': 'servo', 'channel': JAW_PIN,
						'min_angle': float(MIN_ANGLE), 'max_angle': float(MAX_ANGLE),
						'pulse_min': SERVO_MIN, 'pulse_max': SERVO_MAX,
						'rest': float(MIN_ANGLE)}
	if 'eyes' not in PARTS:
		PARTS['eyes'] = {'type': 'led', 'channel': EYES_PIN,
						'min_brightness': 0.0, 'max_brightness': 100.0, 'rest': 0.0,
						'enabled': EYES == 'ON'}
	if 'trigger_out' not in PARTS:
		PARTS['trigger_out'] = {'type': 'led', 'channel': TRIGGER_OUT_PIN,
								'min_brightness': 0.0, 'max_brightness': 100.0, 'rest': 0.0,
								'enabled': TRIGGER_OUT == 'ON'}