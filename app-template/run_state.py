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
    def __init__(self, root, occurrence_key: str, occurrence_title: str, segments: List[sch.EffectiveSegment]):
        self.root = root
        self.occurrence_key = occurrence_key
        self.occurrence_title = occurrence_title
        self.segments = segments

        self.current_index = 0
        self.segment_remaining_seconds = float(segments[0].duration_minutes * 60) if segments else 0.0
        self.running = False
        self.ended = False

        self._last_tick_monotonic: Optional[float] = None
        self._after_id = None
        self._listeners: List[Callable[[], None]] = []

        # Bumped by notify_display_config_changed() - lets a listener that
        # renders a segment's TYPE-SPECIFIC content (ui/run_meeting.py's
        # extra_frame, ui/presentation.py's own) tell "the current segment's
        # config changed in a way that needs a re-render" apart from an
        # ordinary 1Hz tick, without rebuilding on every tick just to be
        # safe. Included in those rebuild signatures alongside current_index.
        self.display_config_version = 0

        # Live-only spotlight state for segment_types.py's IdsType - which
        # single issue (if any) the presentation window shows prominently.
        # Controlled entirely from the Run Meeting screen (see
        # set_focused_issue()); the presentation window is read-only output.
        # Never persisted - resets to None on the next meeting run, like
        # current_index.
        self.focused_issue_id: Optional[str] = None

        # Wall-clock elapsed time for the Meeting Complete summary - separate
        # from segment_remaining_seconds (which gets adjusted by
        # adjust_segment_duration() and so doesn't reflect real elapsed time).
        self._started_monotonic = time.monotonic()
        self._ended_monotonic: Optional[float] = None

    @property
    def elapsed_seconds(self) -> float:
        end = self._ended_monotonic if self._ended_monotonic is not None else time.monotonic()
        return end - self._started_monotonic

    # --- listeners -----------------------------------------------------

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    def notify_display_config_changed(self) -> None:
        """Public hook for a caller that mutated current_segment.config
        directly (e.g. ui/run_meeting.py's live per-segment display
        toggles) rather than through one of this class's own mutator
        methods - pushes the change out to every listener (this screen,
        the indicator bar, the presentation window) the same way any
        other state change does."""
        self.display_config_version += 1
        self._notify()

    def set_focused_issue(self, issue_id: Optional[str]) -> None:
        """Sets (or clears, with None) which issue segment_types.py's IdsType
        spotlights on the presentation window - reuses
        display_config_version so both windows' extra_frame rebuild
        signatures pick this up the same way any other content change does."""
        self.focused_issue_id = issue_id
        self.display_config_version += 1
        self._notify()

    # --- derived state ---------------------------------------------------

    @property
    def current_segment(self) -> Optional[sch.EffectiveSegment]:
        if 0 <= self.current_index < len(self.segments):
            return self.segments[self.current_index]
        return None

    @property
    def is_last_segment(self) -> bool:
        return self.current_index >= len(self.segments) - 1

    @property
    def segment_over_time(self) -> bool:
        return self.segment_remaining_seconds < 0

    @property
    def overall_remaining_seconds(self) -> float:
        """Derived, not stored - "the meeting's remaining time is simply a
        product of the segments," per a real user who explicitly rejected
        having it independently adjustable. It's the current segment's own
        remaining time plus the full (undiminished) duration of every
        segment still to come - so it ticks down every second for free
        (segment_remaining_seconds already does), and immediately reflects
        any adjust_segment_duration() call to ANY segment, current or not,
        with no separate bookkeeping to keep in sync."""
        future = sum(s.duration_minutes * 60 for s in self.segments[self.current_index + 1:])
        return self.segment_remaining_seconds + future

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
        if self.is_last_segment:
            self.stop()
            return
        self.current_index += 1
        self.segment_remaining_seconds = float(self.segments[self.current_index].duration_minutes * 60)
        self._notify()

    def jump_to_segment(self, index: int) -> None:
        if not (0 <= index < len(self.segments)):
            return
        self.current_index = index
        self.segment_remaining_seconds = float(self.segments[index].duration_minutes * 60)
        self._notify()

    def adjust_segment_duration(self, index: int, delta_minutes: int) -> int:
        """Changes segments[index]'s own duration_minutes - not just a
        countdown value, so the change actually sticks if the user jumps
        away and back later (jump_to_segment()/advance_to_next() both
        reset segment_remaining_seconds from this same field). This is
        what lets ANY segment be rebalanced, not just the current one -
        e.g. taking 5 min from IDS and giving it to Scorecard rather than
        extending the whole meeting. Clamped so a segment can never go
        below 1 minute; returns the delta actually applied (may be less
        than requested if clamped). If index is the CURRENTLY ACTIVE
        segment, segment_remaining_seconds is adjusted by the same applied
        delta too, so the live countdown reflects the change immediately
        rather than only the next time this segment starts."""
        if not (0 <= index < len(self.segments)):
            return 0
        segment = self.segments[index]
        new_duration = max(1, segment.duration_minutes + delta_minutes)
        applied_delta = new_duration - segment.duration_minutes
        segment.duration_minutes = new_duration
        if index == self.current_index:
            self.segment_remaining_seconds += applied_delta * 60
        self._notify()
        return applied_delta

    @property
    def total_length_minutes(self) -> int:
        """The meeting's full scheduled length, live - reflects every
        segment adjustment made so far (adjust_segment_duration()), not
        just a static snapshot from when the meeting started."""
        return sch.effective_total_minutes(self.segments)

    def stop(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.running = False
        self.ended = True
        self._ended_monotonic = time.monotonic()
        self._notify()

    def _tick(self) -> None:
        now = time.monotonic()
        elapsed = now - (self._last_tick_monotonic or now)
        self._last_tick_monotonic = now
        self.segment_remaining_seconds -= elapsed
        self._notify()
        if self.running:
            self._after_id = self.root.after(1000, self._tick)
