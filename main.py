"""Vertebral Lumen costume controller for the UNIHIKER.

Run on the UNIHIKER with:
    python3 main.py

For bench development without hardware:
    python3 main.py --simulate
"""

from __future__ import annotations

import argparse
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

from costume_controller.effects import ControllerState, EffectEngine, Mode
from costume_controller.hardware import Hardware
from costume_controller.ui import TouchscreenUI

LED_COUNT = 36  # Change this to the number of WS2812 data nodes on the strip.


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true", help="run with simulated sensors/LEDs")
    args = parser.parse_args()

    hardware = Hardware(simulate=args.simulate, led_count=LED_COUNT)
    state = ControllerState()
    engine = EffectEngine(led_count=LED_COUNT)
    stop = threading.Event()

    ui = TouchscreenUI(state, stop)
    ui.start()

    last = time.monotonic()
    last_report = last
    try:
        while not stop.is_set():
            now = time.monotonic()
            dt = min(now - last, 0.1)
            last = now

            motion = hardware.motion_sample()
            sound = hardware.sound_sample()
            state.ambient_light = hardware.light_sample()
            state.motion_intensity = motion
            state.sound_amplitude = sound

            frame = engine.render(state, motion, sound, dt)
            hardware.write_leds(frame)
            ui.update_indicators(motion, sound, hardware.last_motion_raw, hardware.last_sound_raw)
            if now - last_report >= 0.5:
                print("motion={:.3f} raw_motion={:.3f} sound={:.3f} raw_sound={:.3f} light={:.3f}".format(
                    motion, hardware.last_motion_raw, sound, hardware.last_sound_raw, state.ambient_light))
                last_report = now
            time.sleep(1.0 / 50.0)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        hardware.clear()
        ui.close()


if __name__ == "__main__":
    main()
