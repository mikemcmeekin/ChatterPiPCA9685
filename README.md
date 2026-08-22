# ChatterPi PCA9865
ChatterPi was designed to use GPIO to control a single servo. For projects using PCA9685 you can use this modification. 


# ChatterPi
Flexible Audio Servo Controller using Raspberry Pi (for talking skulls, etc.)
Mike McGurrin

Developed on a Raspberry Pi Model 3 A+ and Pi 4 and tested on the 4 and a Pi Zero W. Given that it runs on a Pi Zero, I believe it will run on any current Pi. 

To use ChatterPi, you can either download the source code, install all the necessary dependencies, and go from there OR you can download a pre-built Raspberry Pi image file to load onto a micro SD card and immediately go from there. 

The image file is too large to put on GitHub. It's called chat.img.gz, and can be found at https://drive.google.com/drive/folders/1njfqegJImeXq-ZoW_yuY0TCJ0bTiwWCA?usp=sharing.

# Introduction

ChatterPi is a software package that turns a Raspberry Pi into an audio servo controller. In other words, the Pi outputs commands to control a servo based on the volume of the audio input. The input can be either stored audio files (in either mono or stereo .wav format) or from an external source, such as a microphone or line level input. One of the uses is to drive animatronic props, such as a skull or a talking bird.

See the documentation for additional information.

# Background: A Brief History of Talking Skull Control

A common prop that still makes a good impact is a talking object, whether a skull or animal. Some lower cost commercial props use a motor and spring. Another approach is to pre-program a complete sequence to match the vocals, but this is very time consuming and if you want to change the vocals, or even just edit them slightly, you need to reprogram the entire sequence. For that reason, the use of an audio servo controller to drive a servomotor controlling the jaw is a very popular approach. There are several variations. One of the earliest use hardware to detect when the audio exceeded a threshold, and then began moving the jaw towards a fully open position, and when the audio went below the threshold, it would begin closing the jaw. &quot;Scary Terry&quot; Simmons may have been the first to develop an [electronic hardware board](http://www.scary-terry.com/audioservo/audioservo.htm) to do this, and [Cowlacious Designs](https://www.cowlacious.com/categories/Scary-Terry-Audio-Servo-Driver/) has continued to improve and sell commercial versions, with many added features such as a built in audio player, various triggering options, and the ability to control LEDs as eyes.

Later, someone named Mike (no relation) combined an Arduino with a hardware volume level board to produce the [Jawduino](http://buttonbanger.com/?page_id=137). This went from having just 2 levels to 4. The original project just took audio in and controlled the servo, but others added extensions to play stored mp3 files and/or randomly move additional servos (for example, [http://batbuddy.org/resources/Halloweenstuff/TalkingSkull.php](http://batbuddy.org/resources/Halloweenstuff/TalkingSkull.php)).

A few years ago, Steve Bjork from Haunt Hackers combined dedicated hardware with a propeller microcontroller to increase the number of levels to almost 256 and also to filter out low and high frequencies that don&#39;t tend to result in jaw movement for spoken sound. The result is the [Wee Little Talker](http://www.haunthackers.com/weelittletalker/index.shtml). This commercial board also has an onboard mp3 player, can be triggered externally, control LED &#39;eyes,&quot; and adds a wide array of features including a voice feedback menu system.

It occurred to me that with current single board computer capabilities and powerful software libraries, it should be possible to incorporate most of the best features of all of these into a single, software-based system running on a Raspberry Pi. The result is ChatterPi. ChatterPi was developed from scratch using the Python language, but ideas for capabilities and features were freely borrowed from previous audio servo controller projects.

# Features
ChaterPi includes the following features

- Audio signal volume controls servo
- Can be started by an external trigger, such as a PIR motion detector
- Can be set to start periodically via an internal timer
- Audio can be from wav files or external input
- Can send an output trigger to start another device when it is triggered
- Output to light LED "eyes" (e.g., for a skull)
- Optionally can play ambient sound tracis between triggering events
- GUI control panel for modifying the configuration parameters
- Utility (via control panel) to maximize the volume of the audio files

If you use ChatterPi, I'd live to hear about it. Post a comment on my blog: https://www.mcgurrin.info/robots/690/ and consider giving this package a star here on GitHub. Thanks!

# Skeleton Scripts & Viam Control

ChatterPi can now drive additional servos (head, arms, ...) declared per-skeleton in `config.ini`, and play timed **scripts** that combine audio with servo motion. The jaw stays audio-driven.

## Per-skeleton hardware
Every piece of hardware is a `[PART <name>]` section in `src/config.ini` (type `servo`/`led`, channel, angle/pulse limits, rest position). Each skeleton carries its own config describing its equipment. Legacy configs without `[PART]` sections still work.

## Scripts
JSON files in `src/scripts/`; `t` is seconds from the start of the script:

```json
{
  "name": "greet",
  "steps": [
    {"t": 0.0, "audio": "v01.wav"},
    {"t": 0.4, "move": {"head": 15, "ms": 400}},
    {"t": 1.2, "move": {"arm_l": 60, "ms": 300}},
    {"t": 4.0, "move": {"head": 0, "ms": 400}}
  ]
}
```

`audio` plays a track (jaw follows the audio level); `move` eases the named parts to the given values over `ms`; `set` jumps immediately.

Run one locally (no Viam): `python src/main.py --script greet`

## Multi-skeleton via Viam
- Each Pi runs `viam-server` with the custom module `src/skeletonModule.py` (see `src/viam-robot-config.example.json`). It exposes a generic service with commands: `play`, `stop`, `list_scripts`, `status`, `get_time`, `set_part`, `rest`.
- `play` accepts `start_epoch` (a shared wall-clock time) plus `offset` (the skeleton's clock offset relative to that clock).
- The conductor (`src/conductor.py`, runs on any PC with viam-sdk — no viam-server needed) measures each skeleton's clock offset with an RTT-corrected `get_time` handshake, picks a common `start_epoch`, and calls `play` on every skeleton so they all start together (millisecond accuracy on a LAN). NTP must be enabled on all machines.
- Legacy trigger/ambient modes (PIR/TIMER/START) still work and automatically yield the hardware while a script is scheduled or playing.
