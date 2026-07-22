"""Shared drag-to-reorder mechanics for a single row list - extracted from
ui/schedule_entry_editor.py's original implementation once Board columns and
statuses (ui/settings.py) needed the identical technique: ButtonPress-1/
B1-Motion/ButtonRelease-1 on a small per-row handle widget, a floating ghost
Toplevel that follows the cursor, a pixel threshold to disambiguate a click
from a drag, and the drop index resolved by comparing the cursor's final
position against each row's midpoint.

orientation defaults to "vertical" (schedule_entry_editor.py's own list, and
settings.py's status-in-column reordering) - comparing Y and using each row's
vertical midpoint/height. settings.py's column strips are laid out
horizontally (side-by-side, not stacked), so column_reorder is constructed
with orientation="horizontal" instead, comparing X and each row's horizontal
midpoint/width. Both branches share every line of logic except which
coordinate/dimension they read - this was a real, latent bug: column
reordering was originally wired through the vertical-only math, comparing
Y positions of strips that all sit at the same Y (same row) - the drop
index computation degenerated to "always index 0" or "always append at the
end" depending only on where vertically within the row you released the
mouse, never reflecting which column you'd actually dragged over.
"""

import tkinter as tk

from ui import theme

DRAG_THRESHOLD_PX = 6


class DragReorder:
    """One instance per rendered list. Call reset_rows() at the start of each
    render, then bind_handle() once per row (in display order) as it's built.
    on_drop(start_index, insert_at) is called only when a real drag ends on a
    different row - the caller splices its own list and re-renders."""

    def __init__(self, ctx, on_drop, orientation: str = "vertical") -> None:
        assert orientation in ("vertical", "horizontal")
        self._ctx = ctx
        self._on_drop = on_drop
        self._vertical = orientation == "vertical"
        self._rows = []  # [(index, row_widget), ...] in display order
        self._state = {"dragging": False, "start_index": None, "ghost": None, "start_pos": 0, "label_text": ""}

    def reset_rows(self) -> None:
        self._rows = []

    def bind_handle(self, handle: tk.Widget, row_widget: tk.Widget, index: int, label_text: str) -> None:
        self._rows.append((index, row_widget))
        handle.bind("<ButtonPress-1>", lambda e: self._on_press(e, index, label_text))
        handle.bind("<B1-Motion>", self._on_motion)
        handle.bind("<ButtonRelease-1>", self._on_release)

    def _pos(self, event) -> int:
        return event.y_root if self._vertical else event.x_root

    def _on_press(self, event, index: int, label_text: str) -> None:
        self._state["dragging"] = False
        self._state["start_index"] = index
        self._state["start_pos"] = self._pos(event)
        self._state["label_text"] = label_text

    def _on_motion(self, event) -> None:
        state = self._state
        if state["start_index"] is None:
            return
        if not state["dragging"] and abs(self._pos(event) - state["start_pos"]) > DRAG_THRESHOLD_PX:
            state["dragging"] = True
            ghost = tk.Toplevel(self._ctx.root)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            tk.Label(
                ghost, text=state["label_text"], background=theme.PRIMARY, foreground="white",
                font=("Segoe UI", 9, "bold"), padx=10, pady=4,
            ).pack()
            state["ghost"] = ghost
        if state["dragging"] and state["ghost"] is not None:
            state["ghost"].geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

    def _on_release(self, event) -> None:
        state = self._state
        if state["ghost"] is not None:
            state["ghost"].destroy()
            state["ghost"] = None

        if state["dragging"]:
            start_index = state["start_index"]
            target_index = self._index_at_point(event)
            if target_index is not None and target_index != start_index:
                insert_at = target_index - 1 if target_index > start_index else target_index
                self._on_drop(start_index, insert_at)

        state["dragging"] = False
        state["start_index"] = None

    def _index_at_point(self, event) -> int:
        point = self._pos(event)
        for index, row in self._rows:
            if not row.winfo_exists():
                continue
            if self._vertical:
                midpoint = row.winfo_rooty() + row.winfo_height() / 2
            else:
                midpoint = row.winfo_rootx() + row.winfo_width() / 2
            if point < midpoint:
                return index
        return len(self._rows)
