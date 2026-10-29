"""Pure-ish LED effect logic. No UNIHIKER or touchscreen imports belong here."""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

RGB = Tuple[int, int, int]


class Mode(str, Enum):
    IDLE = "Idle / Ambient"
    MOTION = "Motion Reactive"
    SOUND = "Sound Reactive"
    COMBINED = "Combined Motion + Sound"


class Pattern(str, Enum):
    FLOW = "Flow"
    SPINE_PULSE = "Spine Pulse"
    MOTION_WAKE = "Motion Wake"
    SOUND_RIPPLE = "Sound Ripple"
    SOUND_BAR = "Sound Bar"
    EMBER_FIELD = "Ember Field"


@dataclass
class ControllerState:
    mode: Mode = Mode.IDLE
    pattern: Pattern = Pattern.FLOW
    brightness: float = 0.35
    primary: RGB = (0, 220, 220)       # cyan
    secondary: RGB = (150, 40, 220)    # violet
    motion_sensitivity: float = 0.55
    sound_sensitivity: float = 0.55
    speed_decay: float = 0.50
    ambient_light: float = 1.0
    motion_intensity: float = 0.0
    sound_amplitude: float = 0.0


@dataclass
class Pulse:
    position: float
    energy: float
    direction: float = 1.0


@dataclass
class Sparkle:
    position: float
    energy: float
    velocity: float = 0.0


class EffectEngine:
    """Renders 36 RGB pixels from normalized sensor signals (0..1)."""

    def __init__(self, led_count: int = 36) -> None:
        self.led_count = led_count
        self.phase = 0.0
        self.travel_phase = 0.0
        self.energy = 0.0
        self._previous_motion = 0.0
        self._previous_sound = 0.0
        # Start with a conservative room-noise assumption. The floor adapts
        # downward/upward over time, but a quiet room does not immediately
        # occupy half of the Sound Bar.
        self._sound_floor = 0.20
        self._sound_peak = 0.35
        self._beat_cooldown = 0.0
        self.pulses: List[Pulse] = []
        self.sparkles: List[Sparkle] = []
        self._sparkle_budget = 0.0
        self._rng = 0x13579BDF
        self._motion_pulse_timer = 0.0
        self._sound_pulse_timer = 0.0
        self.beat_flash = 0.0

    def render(self, state: ControllerState, motion: float, sound: float, dt: float) -> List[RGB]:
        # Sensitivity is a gain control, not just a threshold. This makes the
        # on-screen controls visibly useful during active movement/music.
        # Adaptive sound gate: the floor follows quiet room/crowd noise
        # slowly, while peaks decay faster. This keeps constant ambience from
        # driving the costume but preserves music transients.
        if sound < self._sound_floor + 0.04:
            self._sound_floor += (sound - self._sound_floor) * min(1.0, dt * 0.8)
        else:
            self._sound_floor += (sound - self._sound_floor) * min(1.0, dt * 0.08)
        self._sound_peak = max(sound, self._sound_peak - dt * 0.20)
        sound_range = max(0.12, self._sound_peak - self._sound_floor)
        sound_span = max(0.35, 0.85 - self._sound_floor)
        sound_activity = max(0.0, min(1.0,
                                      (sound - self._sound_floor - 0.06) / sound_span))
        motion_drive = min(1.0, motion * (0.25 + state.motion_sensitivity * 2.5))
        sound_drive = min(1.0, sound_activity * (0.25 + state.sound_sensitivity * 2.5))
        speed = 0.25 + state.speed_decay * 2.0
        self.phase = (self.phase + dt * speed * (1.0 + motion_drive * 3.0)) % 1.0
        if state.pattern == Pattern.SPINE_PULSE:
            # Keep the pulse readable on the 36-pixel strip. Reactive input
            # changes intensity and launches pulses rather than turning this
            # into an unbroken high-speed wave.
            reactive_speed = 0.08 + state.speed_decay * 0.25
            if state.mode in (Mode.MOTION, Mode.COMBINED):
                reactive_speed += motion_drive * 0.55
            if state.mode in (Mode.SOUND, Mode.COMBINED):
                reactive_speed += sound_drive * 0.45
        else:
            reactive_speed = 0.12 + state.speed_decay * 0.45
            if state.mode in (Mode.MOTION, Mode.COMBINED):
                reactive_speed += motion_drive * 3.0
            if state.mode in (Mode.SOUND, Mode.COMBINED):
                reactive_speed += sound_drive * 2.5
        self.travel_phase = (self.travel_phase + dt * reactive_speed) % 1.0

        motion_transient = max(0.0, motion - self._previous_motion * 1.12)
        sound_transient = max(0.0, sound - self._previous_sound * 1.18)
        self._previous_motion, self._previous_sound = motion, sound

        motion_threshold = max(0.025, 0.11 - state.motion_sensitivity * 0.07)
        sound_threshold = max(0.025, 0.11 - state.sound_sensitivity * 0.07)
        self._beat_cooldown = max(0.0, self._beat_cooldown - dt)
        beat_threshold = self._sound_floor + max(0.06, sound_range * 0.35)
        sound_beat = (self._beat_cooldown <= 0.0 and
                      sound > beat_threshold and sound_transient > 0.012)
        if sound_beat:
            self._beat_cooldown = 0.16
        if state.mode in (Mode.MOTION, Mode.COMBINED) and motion_transient > motion_threshold:
            if state.pattern != Pattern.EMBER_FIELD:
                self._add_pulse(min(1.0, motion_transient * (3.0 + state.motion_sensitivity * 4.0)), direction=1.0)
            self._add_sparkle_burst(motion_transient, count=3)
        if state.mode in (Mode.SOUND, Mode.COMBINED) and sound_beat:
            if state.pattern not in (Pattern.EMBER_FIELD, Pattern.SOUND_BAR):
                self._add_pulse(min(1.0, sound_transient * (3.0 + state.sound_sensitivity * 4.0)), direction=1.0)
            if state.pattern != Pattern.SOUND_BAR:
                self._add_sparkle_burst(sound_transient, count=3)
            self.beat_flash = max(self.beat_flash, min(1.0, sound_transient * 5.0 + 0.35))
        self.beat_flash *= max(0.0, 1.0 - dt * 5.0)

        # Keep the response visible during sustained dancing or music, not
        # only on the instant the envelope rises.
        self._motion_pulse_timer -= dt
        self._sound_pulse_timer -= dt
        if state.pattern not in (Pattern.EMBER_FIELD, Pattern.SOUND_BAR) and state.mode in (Mode.MOTION, Mode.COMBINED) and motion_drive > 0.28 and self._motion_pulse_timer <= 0:
            self._add_pulse(min(1.0, 0.45 + motion_drive * 0.75), direction=1.0)
            self._motion_pulse_timer = max(0.35, 0.85 - motion_drive * 0.35)
        if state.pattern not in (Pattern.EMBER_FIELD, Pattern.SOUND_BAR) and state.mode in (Mode.SOUND, Mode.COMBINED) and sound_drive > 0.28 and self._sound_pulse_timer <= 0:
            self._add_pulse(min(1.0, 0.35 + sound_drive * 0.65), direction=1.0)
            self._sound_pulse_timer = max(0.25, 0.65 - sound_drive * 0.25)

        if state.mode == Mode.IDLE:
            mode_energy = 0.10
        elif state.mode == Mode.MOTION:
            mode_energy = 0.10 + motion_drive * 0.95
        elif state.mode == Mode.SOUND:
            mode_energy = 0.10 + sound_drive * 0.95
        else:
            mode_energy = 0.10 + max(motion_drive, sound_drive * 0.9)

        self.energy += (mode_energy - self.energy) * min(1.0, dt * (2.0 + state.speed_decay * 5.0))
        for pulse in self.pulses:
            pulse.position += pulse.direction * dt * (2.0 + state.speed_decay * 5.0 + motion * 3.0)
            pulse.energy *= max(0.0, 1.0 - dt * (1.2 + state.speed_decay * 3.0))
        self.pulses = [p for p in self.pulses if p.energy > 0.015 and -0.3 < p.position < 1.3]

        # Sparkles are deliberate, sensor-driven highlights. They are never
        # generated in Ambient mode, so they cannot be confused with hardware
        # glitches. A tiny deterministic generator keeps this MicroPython-
        # friendly and avoids pulling in a random-number dependency.
        sparkle_drive = 0.0
        if state.pattern == Pattern.SOUND_BAR:
            sparkle_drive = 0.0
        if state.pattern != Pattern.SOUND_BAR and state.mode in (Mode.MOTION, Mode.COMBINED):
            sparkle_drive += motion_drive
        if state.pattern != Pattern.SOUND_BAR and state.mode in (Mode.SOUND, Mode.COMBINED):
            sparkle_drive += sound_drive
        sparkle_rate = 18.0 if state.pattern == Pattern.EMBER_FIELD else 12.0
        sparkle_limit = 24 if state.pattern == Pattern.EMBER_FIELD else 16
        self._sparkle_budget += dt * sparkle_drive * sparkle_rate
        while self._sparkle_budget >= 1.0 and len(self.sparkles) < sparkle_limit:
            self._sparkle_budget -= 1.0
            self._rng = (1664525 * self._rng + 1013904223) & 0xFFFFFFFF
            position = (self._rng / 0xFFFFFFFF)
            self._rng = (1664525 * self._rng + 1013904223) & 0xFFFFFFFF
            velocity = 0.04 + (self._rng / 0xFFFFFFFF) * 0.10 if state.pattern == Pattern.EMBER_FIELD else 0.0
            self.sparkles.append(Sparkle(position, 0.85 + sparkle_drive * 0.35, velocity))
        for sparkle in self.sparkles:
            sparkle.position += sparkle.velocity * dt
            sparkle.energy *= max(0.0, 1.0 - dt * (5.0 + state.speed_decay * 5.0))
        self.sparkles = [s for s in self.sparkles if s.energy > 0.02 and -0.15 < s.position < 1.15]

        frame: List[RGB] = []
        for i in range(self.led_count):
            x = i / max(1, self.led_count - 1)
            # A slow gradient makes cyan and violet both visible in the idle state.
            travel = self.travel_phase
            blend = (math.sin((x + travel) * math.tau) + 1.0) / 2.0
            base = self._mix(state.primary, state.secondary, blend)
            breathe = 0.55 + 0.45 * (math.sin(self.phase * math.tau) + 1.0) / 2.0
            pattern_motion = motion_drive if state.mode in (Mode.MOTION, Mode.COMBINED) else 0.0
            pattern_sound = sound_drive if state.mode in (Mode.SOUND, Mode.COMBINED) else 0.0
            accent_color = state.primary
            sparkle_color = (255, 255, 255)
            accent_mix = 0.0
            if state.pattern == Pattern.FLOW:
                value = self.energy * breathe
            elif state.pattern == Pattern.SPINE_PULSE:
                # Mostly quiet strip with one unmistakable traveling core.
                base = state.secondary
                distance = abs(x - self.travel_phase)
                pulse_band = math.exp(-distance * distance / 0.018)
                value = 0.025 + (0.22 + pattern_motion * 0.75 + pattern_sound * 0.55) * pulse_band
                accent_mix = pulse_band
            elif state.pattern == Pattern.MOTION_WAKE:
                # A bright head and two fading trail segments.
                base = state.secondary
                value = 0.02
                wake_drive = max(0.14, pattern_motion)
                wake_shape = 0.0
                for offset, gain in ((0.0, 1.0), (0.10, 0.45), (0.20, 0.18)):
                    distance = abs(x - ((self.travel_phase - offset) % 1.0))
                    contribution = gain * math.exp(-distance * distance / 0.008)
                    value += wake_drive * contribution
                    wake_shape = max(wake_shape, contribution)
                accent_mix = min(1.0, wake_shape)
            elif state.pattern == Pattern.SOUND_RIPPLE:
                # Distinct alternating bands rather than a smooth gradient.
                base = state.primary
                accent_color = state.secondary
                value = 0.025
                ripple_drive = max(0.14, pattern_sound)
                ripple = 0.5 + 0.5 * math.sin((x + self.travel_phase * 1.4) * math.tau * 3.0)
                value += ripple_drive * (0.18 + 0.75 * ripple)
                accent_mix = ripple * 0.85
            elif state.pattern == Pattern.SOUND_BAR:
                # A clean vertical level meter: LED index 0 is treated as the
                # bottom of the costume and the lit height follows sound.
                base = state.secondary
                # Keep moderate venue levels from filling the entire strip.
                # The bar reaches about 60% even at maximum detected activity.
                bar_level = 0.04 + min(0.56, pattern_sound * 0.56)
                edge_distance = abs(x - bar_level)
                bar_progress = max(0.0, min(1.0, (bar_level - x) / 0.18))
                value = 0.025 + bar_progress * 0.72
                value += self.beat_flash * math.exp(-edge_distance * edge_distance / 0.012)
                accent_color = state.primary
                accent_mix = bar_progress
            elif state.pattern == Pattern.EMBER_FIELD:
                # Low, warm-looking base; the intentional sparkles do the work.
                base = state.secondary
                sparkle_color = state.primary
                value = 0.055 + (pattern_motion + pattern_sound) * 0.24
            if state.pattern == Pattern.FLOW and state.mode in (Mode.MOTION, Mode.COMBINED):
                # A visible moving band follows the wearer's motion.
                band = 0.5 + 0.5 * math.sin((x - self.travel_phase) * math.tau)
                value += motion_drive * 0.80 * band
            if state.mode in (Mode.SOUND, Mode.COMBINED) and state.pattern == Pattern.FLOW:
                # Music raises energy and visibly sweeps a band along the strip.
                audio_band = 0.5 + 0.5 * math.sin((x + self.travel_phase * 1.35) * math.tau)
                value += sound_drive * (0.25 + 0.35 * audio_band)
            for pulse in self.pulses:
                distance = abs(x - pulse.position)
                value += pulse.energy * math.exp(-distance * distance / 0.012)
            sparkle_highlight = 0.0
            for sparkle in self.sparkles:
                distance = abs(x - sparkle.position)
                glow_width = 0.0055 if state.pattern == Pattern.EMBER_FIELD else 0.0025
                sparkle_highlight += sparkle.energy * math.exp(-distance * distance / glow_width)
            # Brightness slider is the ceiling; room light scales it down in
            # darkness so the costume remains comfortable to wear and view.
            ambient_factor = 0.30 + 0.70 * max(0.0, min(1.0, state.ambient_light))
            output = max(0.0, min(1.0, value * state.brightness * ambient_factor))
            pixel_color = self._mix(base, accent_color, accent_mix)
            pixel = self._scale(pixel_color, output)
            if sparkle_highlight > 0.0:
                # Sparkles briefly become near-white points without changing
                # the selected palette underneath.
                highlight = max(0.0, min(1.0, sparkle_highlight * state.brightness))
                pixel = self._mix(pixel, sparkle_color, highlight)
            frame.append(pixel)
        return frame

    def _add_pulse(self, energy: float, direction: float) -> None:
        if len(self.pulses) < 8:
            self.pulses.append(Pulse(position=-0.08, energy=energy, direction=direction))

    def _add_sparkle_burst(self, energy: float, count: int = 2) -> None:
        for _ in range(count):
            if len(self.sparkles) >= 16:
                break
            self._rng = (1664525 * self._rng + 1013904223) & 0xFFFFFFFF
            self.sparkles.append(Sparkle(self._rng / 0xFFFFFFFF,
                                         min(1.0, 0.75 + energy * 2.0)))

    @staticmethod
    def _mix(a: RGB, b: RGB, amount: float) -> RGB:
        return tuple(round(a[i] * (1 - amount) + b[i] * amount) for i in range(3))  # type: ignore[return-value]

    @staticmethod
    def _scale(color: RGB, amount: float) -> RGB:
        return tuple(max(0, min(255, round(c * amount))) for c in color)  # type: ignore[return-value]
