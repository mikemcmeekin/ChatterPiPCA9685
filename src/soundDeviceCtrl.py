# -*- coding: utf-8 -*-
"""
Created on Sun May 17 22:19:49 2020
@author: Mike McGurrin
Updated to improve speed and run on Pi Zero 7/13/2020
"""
#import wave
import time
#import pyaudio
import atexit
import threading
import sounddevice as sd
import soundfile as sf
import numpy as np
from bandpassFilter import BPFilter
import config as c
from servo import StandardServo
from led import LEDControl
import logging
from threading import Thread

c.update()

class AUDIO:
    def __init__(self):
        self.jaw = StandardServo(channel=c.JAW_PIN, min_angle=c.MIN_ANGLE, 
                    max_angle=c.MAX_ANGLE, initial_angle=None, 
                    min_pulse_width=c.SERVO_MIN,
                    max_pulse_width=c.SERVO_MAX)
        self.bp = BPFilter()
        self.eyesPin = LEDControl(channel=c.EYES_PIN)
        # flipping MIN_ANGLE and MAX_ANGLE in settings changes direction of servo movement BUT
        # must use unflipped values in calculating the amount of jaw movement
        if c.MIN_ANGLE > c.MAX_ANGLE:
            self.j_min = c.MIN_ANGLE
            self.j_max = c.MAX_ANGLE
        else:
            self.j_min = c.MAX_ANGLE
            self.j_max = c.MIN_ANGLE          
        
    def update_jaw(self):
        self.jaw = StandardServo(channel=c.JAW_PIN, min_angle=c.MIN_ANGLE, 
                    max_angle=c.MAX_ANGLE, initial_angle=None, 
                    min_pulse_width=c.SERVO_MIN,
                    max_pulse_width=c.SERVO_MAX)
        if c.MIN_ANGLE > c.MAX_ANGLE:
            self.j_min = c.MIN_ANGLE
            self.j_max = c.MAX_ANGLE
        else:
            self.j_min = c.MAX_ANGLE
            self.j_max = c.MIN_ANGLE    
           
    def play_vocal_track(self, filename=None):
        # Used for both threshold (Scary Terry style) and multi-level (jawduino style)
        def get_avg(levels, channels):
            """Gets and returns the average volume for the frame (chunk).
            for stereo channels, only looks at the right channel (channel 1)"""
            # Apply bandpass filter if STYLE=2
            if c.STYLE == 2:
                levels = self.bp.filter_data(levels)
            levels = np.absolute(levels)
            if channels == 1:
                avg_volume = np.sum(levels)//len(levels)
            elif channels == 2:
                rightLevels = levels[1::2]
                avg_volume = np.sum(rightLevels)//len(rightLevels)
            return(avg_volume)
         
        def get_target(data, channels):
            levels = abs(np.frombuffer(data, dtype='<i2'))
            volume = get_avg(levels, channels)
            jawStep = (self.j_max - self.j_min) / 3
            if c.STYLE == 0:      # Scary Terry style single threshold
                if volume > c.THRESHOLD: 
                    jawTarget = self.j_max
                else: 
                    jawTarget = self.j_min
            elif c.STYLE == 1:     # Jawduino style multi-level or Wee Talker bandpss multi-level   
                if volume > c.LEVEL3:
                    jawTarget = self.j_max
                elif volume > c.LEVEL2:
                    jawTarget = self.j_min + 2 * jawStep
                elif volume > c.LEVEL1:
                    jawTarget = self.j_min + jawStep
                else:
                    jawTarget = self.j_min
            elif c.STYLE == 2:     # Mikes variable
                if volume > c.LEVEL3:
                    jawTarget = self.j_max
                    print("max volume was reached " + str(volume))
                elif volume > c.THRESHOLD:
                    jawTarget = int((volume / c.LEVEL3) * self.j_max)
                    print("jawTarget was " + str(volume / c.LEVEL3) + " vol " + str(volume) + " lvl " + str(c.LEVEL3))
                else:
                    jawTarget = self.j_min
            else:     # Jawduino style multi-level or Wee Talker bandpss multi-level   
                if volume > c.FIlTERED_LEVEL3:
                    jawTarget = self.j_max
                elif volume > c.FIlTERED_LEVEL2:
                    jawTarget = self.j_min + 2 * jawStep
                elif volume > c.FIlTERED_LEVEL1:
                    jawTarget = self.j_min + jawStep
                else:
                    jawTarget = self.j_min   
            return jawTarget      
                

           
               
        def normalEnd():
            #self.stream.stop_stream()
            self.stream.close()
            #if (c.SOURCE == 'FILES'):
                #wf.close()
            self.jaw.set_angle(0)  
            
        def cleanup():
            normalEnd()
            #self.p.terminate()
            self.jaw.close()

        event = threading.Event()

        try:
            atexit.register(cleanup)                      
            #Playing from wave file
            current_frame = 0
            lastJawTarget = 0
            def filesCallback(outdata, frames, times, status):
                nonlocal latest_time, current_frame, lastJawTarget
                #global current_frame
                 # Only proces jaw movements 50x per second, to avoid buffer overruns
                now = time.monotonic()
                chunksize = min(len(data) - current_frame, frames)
                if now - latest_time > 0.3:
                    latest_time = now   
                    jawTarget = get_target(data[current_frame:current_frame + chunksize], 1)
                    angle = 180-jawTarget
                    if abs(angle - lastJawTarget) < 6 :
                        angle = int(angle *.8)
                    #self.jaw.set_angle(angle)
                    
                    thread = Thread(target=self.jaw.set_angle, args=[angle])
                    # run the thread
                    thread.start()
                    lastJawTarget = angle
                    self.eyesPin.set_brightness((jawTarget/180)*100)
               
                outdata[:chunksize] = data[current_frame:current_frame + chunksize]
                if chunksize < frames:
                    outdata[chunksize:] = 0
                    raise sd.CallbackStop()
                current_frame += chunksize


            data, wf = sf.read(filename, always_2d=True)
            #file_sw = wf.getsampwidth()  
            # New code to support only process jaw movements 50x per second
            start_time = time.monotonic() 
            latest_time = start_time                                 
            self.stream = sd.OutputStream(samplerate=wf, latency='low', channels=data.shape[1], blocksize=0,
                    callback=filesCallback, finished_callback=event.set, prime_output_buffers_using_stream_callback=True)  
            with self.stream:
                event.wait()  # Wait until playback is finished                                    
            normalEnd() 
        except (KeyboardInterrupt, SystemExit):
            print("An exception occurred")
            cleanup()                 
        

            
