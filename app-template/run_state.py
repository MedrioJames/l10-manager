"""Live meeting-run timer/controller. In-memory only - never serialized to
Data/ (see CLAUDE.md): if the app closes mid-meeting, the next launch has
no active run, and the user starts over from Prep. That's an accepted v1
tradeoff, not an oversight - it avoids adding more disk writes to the same
Google-Drive-synced folder that already caused a real data-loss scare, for
a feature whose worst failure mode is "glance at a phone clock instead."

A MeetingRunState lives on ui.shell.AppContext (ctx.run_state), which is
the one object every screen receives that survives AppShell.navigate()'s
teardown of ctx.content - that's what lets the timer keep ticking no
matter what screen the user is looking at. Ticking is driven by a single
root.after(1000, ...) loop using time.monotonic() (never wall-clock, so
system clock changes/laptop sleep don't cause jumps); it never touches a
Tkinter widget directly, only numbers and listener callbacks, so any UI
surface (the Run screen, the persistent indicator bar, the presentation
window) can subscribe independently via add_listener()/remove_listener()
and is responsible for guarding its own widget lifetime.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

import schedule as sch


def format_mmss(seconds: float) -> str:
    total = max(0, int(round(abs(seconds))))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


class MeetingRunState:
    def __init__(self, root, occurrence_key: str, occurrence_title: str, sections: List[sch.EffectiveSection]):
        self.root = root
        self.occurrence_key = occurrence_key
        self.occurrence_title = occurrence_title
        self.sections = sections

        self.current_index = 0
        self.overall_remaining_seconds = float(sum(s.duration_minutes * 60 for s in sections))
        self.section_remaining_seconds = float(sections[0].duration_minutes * 60) if sections else 0.0
        self.running = False
        self.ended = False

        self._last_tick_monotonic: Optional[float] = None
        self._after_id = None
        self._listeners: List[Callable[[], None]] = []

    # --- listeners -----------------------------------------------------

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    # --- derived state ---------------------------------------------------

    @property
    def current_section(self) -> Optional[sch.EffectiveSection]:
        if 0 <= self.current_index < len(self.sections):
            return self.sections[self.current_index]
        return None

    @property
    def is_last_section(self) -> bool:
        return self.current_index >= len(self.sections) - 1

    @property
    def section_over_time(self) -> bool:
        return self.section_remaining_seconds < 0

    @property
    def overall_over_time(self) -> bool:
        return self.overall_remaining_seconds < 0

    # --- controls --------------------------------------------------------

    def resume(self) -> None:
        if self.running or self.ended:
            return
        self.running = True
        self._last_tick_monotonic = time.monotonic()
        self._after_id = self.root.after(1000, self._tick)
        self._notify()

    def pause(self) -> None:
        if not self.running:
            return
        self.running = False
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._notify()

    def toggle_start_pause(self) -> None:
        if self.running:
            self.pause()
        else:
            self.resume()

    def advance_to_next(self) -> None:
        if self.is_last_section:
            self.stop()
            return
        self.current_index += 1
        self.section_remaining_seconds = float(self.sections[self.current_index].duration_minutes * 60)
        self._notify()

    def jump_to_section(self, index: int) -> None:
        if not (0 <= index < len(self.sections)):
            return
        self.current_index = index
        self.section_remaining_seconds = float(self.sections[index].duration_minutes * 60)
        self._notify()

    def adjust_overall_time(self, delta_seconds: float) -> None:
        self.overall_remaining_seconds += delta_seconds
        self._notify()

    def adjust_section_time(self, delta_seconds: float) -> None:
        self.section_remaining_seconds += delta_seconds
        self._notify()

    def stop(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.running = False
        self.ended = True
        self._notify()

    def _tick(self) -> None:
        now = time.monotonic()
        elapsed = now - (self._last_tick_monotonic or now)
        self._last_tick_monotonic = now
        self.section_remaining_seconds -= elapsed
        self.overall_remaining_seconds -= elapsed
        self._notify()
        if self.running:
            self._after_id = self.root.after(1000, self._tick)
