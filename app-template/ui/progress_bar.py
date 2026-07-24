"""A small horizontal meeting-progress bar - shows how far into the whole
agenda the current run is, with a thin tick mark at each segment boundary,
so a glance answers "where are we" without reading the countdown. Shared by
ui/run_meeting.py (always shown - "my view") and ui/presentation.py
(gated on MeetingConfig.show_progress_bar_in_presentation - a real user
wanted the choice, since some teams may not want the room seeing exactly
how far behind/ahead a segment is running).

A plain tk.Canvas, not a RoundedCard/RoundedButton - there's no embedded
child content and no interactivity here, just filled rectangles and lines,
so the extra machinery those widgets carry (child-window sizing
negotiation, hover/press state) would be pure overhead.
"""

import tkinter as tk

from ui import theme

HEIGHT = 10


class ProgressBar(tk.Canvas):
    def __init__(self, parent, height: int = HEIGHT, background=None):
        outer_background = background
        if outer_background is None:
            try:
                outer_background = parent.cget("background")
            except tk.TclError:
                outer_background = theme.BG
        super().__init__(parent, height=height, background=outer_background, highlightthickness=0, bd=0)
        self._state = None  # (segments, current_index, segment_remaining_seconds)
        self.bind("<Configure>", lambda _e: self._redraw())

    def update_state(self, segments, current_index: int, segment_remaining_seconds: float) -> None:
        self._state = (segments, current_index, segment_remaining_seconds)
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        if not self._state:
            return
        segments, current_index, segment_remaining_seconds = self._state
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or not segments:
            return

        total_seconds = sum(s.duration_minutes * 60 for s in segments)
        if total_seconds <= 0:
            return
        elapsed_before = sum(s.duration_minutes * 60 for s in segments[:current_index])
        current_duration = segments[current_index].duration_minutes * 60 if 0 <= current_index < len(segments) else 0
        elapsed_current = max(0.0, current_duration - segment_remaining_seconds)
        elapsed = elapsed_before + elapsed_current
        over_time = elapsed > total_seconds
        fraction = min(1.0, elapsed / total_seconds)

        self.create_rectangle(0, 0, width, height, fill=theme.LINE, outline="")
        fill_width = fraction * width
        if fill_width > 0:
            self.create_rectangle(
                0, 0, fill_width, height, fill=theme.DANGER if over_time else theme.PRIMARY, outline="",
            )

        # Segment-boundary tick marks - every boundary except the very last
        # (the right edge of the bar already reads as "end of meeting").
        cumulative = 0
        for segment in segments[:-1]:
            cumulative += segment.duration_minutes * 60
            x = (cumulative / total_seconds) * width
            self.create_line(x, 0, x, height, fill=theme.CARD_BG, width=1)
