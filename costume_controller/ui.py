"""UNIHIKER touchscreen controls. UI callbacks mutate ControllerState only."""

from __future__ import annotations

import threading
from typing import List, Tuple

from .effects import ControllerState, Mode, Pattern, RGB


class _ButtonParts:
    """Small wrapper so a compact button can update its label and styling."""

    def __init__(self, fill, outline, label) -> None:
        self.fill, self.outline, self.label = fill, outline, label

    def config(self, **kwargs) -> None:
        self.label.config(**kwargs)

    def selected(self, active: bool) -> None:
        if active:
            self.fill.config(color="#164B5A")
            self.outline.config(color="#72E7E7")
        else:
            self.fill.config(color="#172331")
            self.outline.config(color="#3B617A")


class TouchscreenUI:
    PRIMARY_PALETTE = [
        ("Cyan", (0, 220, 220)),
        ("Blue", (35, 100, 255)),
        ("Magenta", (230, 30, 180)),
        ("Amber", (255, 120, 20)),
        ("White", (255, 255, 255)),
        ("Green", (40, 240, 100)),
    ]
    SECONDARY_PALETTE = [
        ("Violet", (150, 40, 220)),
        ("Pink", (255, 20, 100)),
        ("Lime", (120, 255, 30)),
        ("Gold", (255, 180, 20)),
        ("Ice", (80, 190, 255)),
        ("Red", (255, 25, 25)),
    ]

    def __init__(self, state: ControllerState, stop: threading.Event) -> None:
        self.state, self.stop = state, stop
        self.gui = None
        self.labels = {}
        self.buttons = {}

    def start(self) -> None:
        try:
            from unihiker import GUI
            self.gui = GUI()
            self._build()
        except Exception as exc:
            print("Touchscreen UI unavailable:", exc)

    def _build(self) -> None:
        g = self.gui
        # M10's screen is 240x320 in portrait orientation.
        g.fill_rect(x=0, y=0, w=240, h=320, color="#05070D")
        g.draw_text(x=5, y=3, text="VERTEBRAL LUMEN", color="#7DE7E7", font_size=15)
##        g.draw_text(x=5, y=23, text="MODE", color="#657080", font_size=10)
        modes = list(Mode)
        for i, mode in enumerate(modes):
            self.buttons["mode_" + mode.name] = self._button(
                5, 35 + i * 25, 230, 22, mode.value,
                lambda m=mode: self._set_mode(m))
        self._highlight_mode()
        controls = [("brightness", "Bright", 143), ("motion_sensitivity", "Motion sens.", 162),
                    ("sound_sensitivity", "Sound sens.", 181), ("speed_decay", "Speed/decay", 200)]
        for name, title, y in controls:
            g.draw_text(x=5, y=y + 3, text=title, color="#C2CBD8", font_size=9)
            self._button(88, y, 28, 17, "-", lambda n=name: self._adjust(n, -0.10))
            self.labels[name] = g.draw_text(x=142, y=y + 3, text=self._percent(name),
                                            color="#9FE8FF", font_size=9, origin="center")
            self._button(160, y, 28, 17, "+", lambda n=name: self._adjust(n, 0.10))
        self.buttons["pattern"] = self._button(5, 222, 230, 18, "Pattern: Flow", self._cycle_pattern)
        self.buttons["primary"] = self._button(5, 243, 110, 18, "Primary: Cyan", self._cycle_primary)
        self.buttons["secondary"] = self._button(120, 243, 115, 18, "Secondary: Violet", self._cycle_secondary)
        self.labels["motion"] = g.draw_text(x=5, y=268, text="Motion 0% / raw 0%", color="#D7E6FF", font_size=9)
        self.labels["sound"] = g.draw_text(x=5, y=283, text="Mic 0% / raw 0%", color="#D7E6FF", font_size=9)
        self.labels["status"] = g.draw_text(x=5, y=301, text="Idle / Ambient", color="#7DE7E7", font_size=9)

    def _button(self, x, y, w, h, text, callback) -> None:
        """Compact outlined button with the label as the touch target."""
        fill = self.gui.fill_round_rect(x=x, y=y, w=w, h=h, r=3,
                                        color="#172331", onclick=callback)
        outline = self.gui.draw_round_rect(x=x, y=y, w=w, h=h, r=3,
                                           color="#3B617A", onclick=callback)
        label = self.gui.draw_text(x=x, y=y, w=w, text=text,
                                   color="#D7E6FF", font_size=8,
                                   onclick=callback)
        return _ButtonParts(fill, outline, label)

    def _percent(self, name: str) -> str:
        return f"{getattr(self.state, name) * 100:3.0f}%"

    def _adjust(self, name: str, delta: float) -> None:
        value = max(0.0, min(1.0, getattr(self.state, name) + delta))
        setattr(self.state, name, value)
        print("UI {} = {:.0f}%".format(name, value * 100))
        label = self.labels.get(name)
        if label is not None:
            label.config(text=self._percent(name))

    def _cycle_primary(self) -> None:
        colors = self.PRIMARY_PALETTE
        current = next((i for i, (_, color) in enumerate(colors) if color == self.state.primary), -1)
        name, color = colors[(current + 1) % len(colors)]
        self.state.primary = color
        self.buttons["primary"].config(text="Primary: " + name)

    def _cycle_secondary(self) -> None:
        colors = self.SECONDARY_PALETTE
        current = next((i for i, (_, color) in enumerate(colors) if color == self.state.secondary), -1)
        name, color = colors[(current + 1) % len(colors)]
        self.state.secondary = color
        self.buttons["secondary"].config(text="Secondary: " + name)

    def _cycle_pattern(self) -> None:
        patterns = list(Pattern)
        current = patterns.index(self.state.pattern)
        self.state.pattern = patterns[(current + 1) % len(patterns)]
        self.buttons["pattern"].config(text="Pattern: " + self.state.pattern.value)
        print("UI pattern = " + self.state.pattern.value)

    def _set_mode(self, mode: Mode) -> None:
        self.state.mode = mode
        self._highlight_mode()
        label = self.labels.get("status")
        if label is not None:
            label.config(text=mode.value)

    def _highlight_mode(self) -> None:
        for mode in Mode:
            button = self.buttons.get("mode_" + mode.name)
            if button is not None:
                button.selected(mode == self.state.mode)

    def update_indicators(self, motion: float, sound: float, raw_motion: float = 0.0,
                          raw_sound: float = 0.0) -> None:
        if not self.gui:
            return
        for key, text in (("motion", f"Motion {motion * 100:3.0f}% / raw {raw_motion * 100:3.0f}%"),
                          ("sound", f"Mic {sound * 100:3.0f}% / raw {raw_sound * 100:3.0f}%")):
            label = self.labels.get(key)
            if label is not None:
                label.config(text=text)

    def close(self) -> None:
        # GUI objects generally close with the process on UNIHIKER.
        self.gui = None
