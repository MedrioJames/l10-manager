"""Shared drag-to-reorder mechanics for vertical row lists - extracted from
ui/schedule_entry_editor.py's original implementation once Board columns and
statuses (ui/settings.py) needed the identical technique: ButtonPress-1/
B1-Motion/ButtonRelease-1 on a small per-row handle widget, a floating ghost
Toplevel that follows the cursor, a pixel threshold to disambiguate a click
from a drag, and the drop index resolved by comparing the cursor's final Y
against each row's vertical midpoint.
"""

import tkinter as tk

from ui import theme

DRAG_THRESHOLD_PX = 6


class DragReorder:
    """One instance per rendered list. Call reset_rows() at the start of each
    render, then bind_handle() once per row (in display order) as it's built.
    on_drop(start_index, insert_at) is called only when a real drag ends on a
    different row - the caller splices its own list and re-renders."""

    def __init__(self, ctx, on_drop) -> None:
        self._ctx = ctx
        self._on_drop = on_drop
        self._rows = []  # [(index, row_widget), ...] in display order
        self._state = {"dragging": False, "start_index": None, "ghost": None, "start_y": 0, "label_text": ""}

    def reset_rows(self) -> None:
        self._rows = []

    def bind_handle(self, handle: tk.Widget, row_widget: tk.Widget, index: int, label_text: str) -> None:
        self._rows.append((index, row_widget))
        handle.bind("<ButtonPress-1>", lambda e: self._on_press(e, index, label_text))
        handle.bind("<B1-Motion>", self._on_motion)
        handle.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event, index: int, label_text: str) -> None:
        self._state["dragging"] = False
        self._state["start_index"] = index
        self._state["start_y"] = event.y_root
        self._state["label_text"] = label_text

    def _on_motion(self, event) -> None:
        state = self._state
        if state["start_index"] is None:
            return
        if not state["dragging"] and abs(event.y_root - state["start_y"]) > DRAG_THRESHOLD_PX:
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

    def _on_release(self, _event) -> None:
        state = self._state
        if state["ghost"] is not None:
            state["ghost"].destroy()
            state["ghost"] = None

        if state["dragging"]:
            start_index = state["start_index"]
            target_index = self._index_at_point(_event.y_root)
            if target_index is not None and target_index != start_index:
                insert_at = target_index - 1 if target_index > start_index else target_index
                self._on_drop(start_index, insert_at)

        state["dragging"] = False
        state["start_index"] = None

    def _index_at_point(self, root_y: int) -> int:
        for index, row in self._rows:
            if not row.winfo_exists():
                continue
            midpoint = row.winfo_rooty() + row.winfo_height() / 2
            if root_y < midpoint:
                return index
        return len(self._rows)
