"""Hardware boundary: WS2812 output, microphone, accelerometer and gyro."""

from __future__ import annotations

import math
import time
from typing import List, Tuple

RGB = Tuple[int, int, int]


class Hardware:
    """Best-effort adapter for common UNIHIKER/pinpong library variants.

    The LED strip is intentionally not powered by the UNIHIKER. Provide an
    external regulated 5 V supply, tie its ground to UNIHIKER ground, and use
    the 74AHCT125 plus ~470 ohm series resistor on D21.
    """

    def __init__(self, simulate: bool = False, led_count: int = 36) -> None:
        self.simulate = simulate
        self.led_count = led_count
        self.strip = None
        self.sensor = None
        self.audio = None
        self.light_sensor = None
        self._motion_envelope = 0.0
        self._sound_envelope = 0.0
        self._light_envelope = 1.0
        self.last_motion_raw = 0.0
        self.last_sound_raw = 0.0
        if not simulate:
            self._init_real_hardware()

    def _init_real_hardware(self) -> None:
        try:
            from pinpong.board import Board, Pin
            Board().begin()
            try:
                from pinpong.board import NeoPixel
                self.strip = NeoPixel(Pin(21), self.led_count)
            except (ImportError, AttributeError, TypeError):
                # Some pinpong releases expose the strip class in an extension.
                from pinpong.extension.unihiker import NeoPixel
                self.strip = NeoPixel(Pin(21), self.led_count)
        except Exception as exc:
            raise RuntimeError("Could not initialize D21 WS2812 hardware: " + str(exc)) from exc

        # Optional APIs are probed so the rest of the application stays stable
        # across UNIHIKER image/library versions.
        try:
            # M10 exposes these singleton objects from pinpong's UNIHIKER
            # extension (get_x/get_y/get_z and get_strength are the standard
            # documented API).
            from pinpong.extension.unihiker import accelerometer, gyroscope
            self.sensor = (accelerometer, gyroscope)
        except Exception:
            self.sensor = None
        try:
            from unihiker import Audio
            self.audio = Audio()
        except Exception:
            self.audio = None
        try:
            from pinpong.extension.unihiker import light
            self.light_sensor = light
        except Exception:
            self.light_sensor = None

    def write_leds(self, frame: List[RGB]) -> None:
        if self.simulate:
            return
        for i, color in enumerate(frame):
            self.strip[i] = color
        show = getattr(self.strip, "show", None)
        if show:
            show()

    def motion_sample(self) -> float:
        if self.simulate:
            self.last_motion_raw = 0.35 + 0.25 * (math.sin(time.monotonic() * 1.7) + 1) / 2
            return self.last_motion_raw
        values = self._read_motion_values()
        # Acceleration magnitude around 1 g is stationary; gyro magnitude adds
        # deliberate rotation. Normalize and clamp to a useful envelope.
        ax, ay, az, gx, gy, gz = values
        accel_delta = abs(math.sqrt(ax * ax + ay * ay + az * az) - 1.0)
        gyro = math.sqrt(gx * gx + gy * gy + gz * gz) / 180.0
        raw = min(1.0, accel_delta * 1.8 + gyro)
        self.last_motion_raw = raw
        # Fast attack catches gestures; slower release prevents sensor noise
        # from making the strip visibly flicker.
        rate = 0.35 if raw < self._motion_envelope else 8.0
        self._motion_envelope += (raw - self._motion_envelope) * min(1.0, rate * 0.02)
        return self._motion_envelope

    def _read_motion_values(self):
        if not self.sensor:
            return (0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        accel_sensor, gyro_sensor = self.sensor
        def read(sensor, names, default):
            for name in names:
                method = getattr(sensor, name, None)
                if callable(method):
                    result = method()
                    return float(result)
            return default
        accel = tuple(read(accel_sensor, (f"get_{axis}",), 1.0 if axis == "z" else 0.0)
                      for axis in ("x", "y", "z"))
        gyro = tuple(read(gyro_sensor, (f"get_{axis}",), 0.0)
                     for axis in ("x", "y", "z"))
        return (*accel, *gyro)

    def sound_sample(self) -> float:
        if self.simulate:
            self.last_sound_raw = max(0.0, min(1.0, 0.08 + 0.06 * (math.sin(time.monotonic() * 2.3) + 1)))
            return self.last_sound_raw
        if not self.audio:
            return 0.0
        for name in ("sound_level", "get_amplitude", "get_volume", "get_audio_level"):
            method = getattr(self.audio, name, None)
            if callable(method):
                try:
                    value = float(method())
                    raw = max(0.0, min(1.0, value / 100.0 if value > 1 else value))
                    self.last_sound_raw = raw
                    # Audio.sound_level() is a coarse 0..100 level. A short
                    # attack and longer release gives a stable envelope while
                    # preserving claps/bass hits as transients.
                    rate = 0.45 if raw < self._sound_envelope else 10.0
                    self._sound_envelope += (raw - self._sound_envelope) * min(1.0, rate * 0.02)
                    return self._sound_envelope
                except (TypeError, ValueError):
                    pass
        return 0.0

    def light_sample(self) -> float:
        """Return a smoothed ambient-light reading normalized to 0..1."""
        if self.simulate:
            raw = 0.35 + 0.25 * (math.sin(time.monotonic() * 0.18) + 1.0) / 2.0
        elif self.light_sensor is not None:
            try:
                raw = max(0.0, min(1.0, float(self.light_sensor.read()) / 4095.0))
            except (AttributeError, TypeError, ValueError):
                raw = 1.0
        else:
            raw = 1.0
        self._light_envelope += (raw - self._light_envelope) * 0.02
        return self._light_envelope

    def clear(self) -> None:
        if self.strip is not None:
            self.write_leds([(0, 0, 0)] * self.led_count)
