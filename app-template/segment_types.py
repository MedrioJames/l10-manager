"""Segment types - the extensible catalog of "kinds" a Segment (see
schedule.py) can be. Each type is one class: its Config dataclass defines
what's configurable, and the type owns how that config is edited (falls
back to an auto-generated form reflecting Config's fields if the type
doesn't need anything custom), how the live Run screen renders it, and how
the presentation window renders it. Adding a new type is "write the class,
you have what you need" - no other file needs to change.

Deliberately no `from __future__ import annotations` in this module -
render_settings_form's auto-generated form reflects on
dataclasses.fields(self.Config)[i].type, which needs real type objects
(bool/str/int/List[str]), not string annotations.

Rocks/Scorecard Configs are deliberately display-setting-only (show_owner,
show_trend_arrows) - real rock/scorecard data doesn't exist as a feature
yet (ui/placeholders.py stubs), so there's nothing else to store here.
"""

import dataclasses
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Type

from ui import icon_button


class SegmentType:
    type_id: str = "generic"
    display_name: str = "Generic"
    Config: Optional[Type] = None
    default_duration_minutes: int = 5

    def default_config(self) -> dict:
        return dataclasses.asdict(self.Config()) if self.Config else {}

    def render_settings_form(self, parent, values: dict, on_change) -> None:
        """Default: reflects over Config's fields. `values` is mutated in
        place; on_change() fires after every edit. Override only if a type
        wants a custom-looking form."""
        if not self.Config:
            return
        for f in dataclasses.fields(self.Config):
            if f.name not in values:
                values[f.name] = f.default if f.default is not dataclasses.MISSING else None
            if f.type is bool:
                self._render_bool_field(parent, values, f.name, on_change)
            elif f.type is int:
                self._render_int_field(parent, values, f.name, on_change)
            elif f.type == List[str]:
                self._render_list_field(parent, values, f.name, on_change)
            else:
                self._render_str_field(parent, values, f.name, on_change)

    def render_run_view(self, parent, effective_segment) -> None:
        """Extra content shown on the Run Meeting screen below the
        countdown, for this specific segment. Default: nothing extra."""
        return None

    def render_presentation_view(self, parent, effective_segment) -> None:
        """Extra content shown on the presentation window below the
        countdown. Default: nothing extra."""
        return None

    # --- default form field renderers -------------------------------

    @staticmethod
    def _label_for(field_name: str) -> str:
        return field_name.replace("_", " ").capitalize()

    def _render_bool_field(self, parent, values, key, on_change) -> None:
        var = tk.BooleanVar(value=bool(values.get(key)))

        def on_toggle() -> None:
            values[key] = var.get()
            on_change()

        ttk.Checkbutton(parent, text=self._label_for(key), variable=var, command=on_toggle).pack(anchor="w", pady=(0, 6))

    def _render_str_field(self, parent, values, key, on_change) -> None:
        ttk.Label(parent, text=self._label_for(key), style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 2))
        var = tk.StringVar(value=str(values.get(key) or ""))

        def on_edit(*_args) -> None:
            values[key] = var.get()
            on_change()

        var.trace_add("write", on_edit)
        ttk.Entry(parent, textvariable=var, width=36).pack(anchor="w", pady=(0, 8))

    def _render_int_field(self, parent, values, key, on_change) -> None:
        ttk.Label(parent, text=self._label_for(key), style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 2))
        var = tk.StringVar(value=str(values.get(key) or 0))

        def on_edit(*_args) -> None:
            try:
                values[key] = int(var.get())
            except ValueError:
                return
            on_change()

        var.trace_add("write", on_edit)
        ttk.Spinbox(parent, from_=0, to=999, width=8, textvariable=var).pack(anchor="w", pady=(0, 8))

    def _render_list_field(self, parent, values, key, on_change) -> None:
        ttk.Label(parent, text=self._label_for(key), style="SectionHeading.TLabel").pack(anchor="w", pady=(0, 4))
        values.setdefault(key, [])
        rows_frame = ttk.Frame(parent)
        rows_frame.pack(fill="x", pady=(0, 4))

        def render_rows() -> None:
            for child in rows_frame.winfo_children():
                child.destroy()
            for idx, item in enumerate(values[key]):
                row = ttk.Frame(rows_frame)
                row.pack(fill="x", pady=1)
                var = tk.StringVar(value=item)

                def on_edit(*_args, i=idx, v=var) -> None:
                    values[key][i] = v.get()
                    on_change()

                var.trace_add("write", on_edit)
                ttk.Entry(row, textvariable=var, width=30).pack(side="left", padx=(0, 4))
                icon_button.icon_button(
                    row, icon_button.GLYPH_DELETE, lambda i=idx: remove_item(i), danger=True,
                ).pack(side="left")

        def remove_item(idx: int) -> None:
            del values[key][idx]
            render_rows()
            on_change()

        def add_item() -> None:
            values[key].append("")
            render_rows()
            on_change()

        render_rows()
        ttk.Button(parent, text="+ Add", style="Secondary.TButton", command=add_item).pack(anchor="w", pady=(0, 10))


# --- Built-in types ---------------------------------------------------


@dataclasses.dataclass
class HeadlinesConfig:
    show_people: bool = True


class HeadlinesType(SegmentType):
    type_id = "headlines"
    display_name = "Headlines"
    Config = HeadlinesConfig


@dataclasses.dataclass
class CoreValuesConfig:
    values: List[str] = dataclasses.field(default_factory=list)


class CoreValuesType(SegmentType):
    type_id = "core_values"
    display_name = "Core Values"
    Config = CoreValuesConfig


@dataclasses.dataclass
class RocksConfig:
    show_owner: bool = True


class RocksType(SegmentType):
    type_id = "rocks"
    display_name = "Rock Review"
    Config = RocksConfig


@dataclasses.dataclass
class ScorecardConfig:
    show_trend_arrows: bool = True


class ScorecardType(SegmentType):
    type_id = "scorecard"
    display_name = "Scorecard"
    Config = ScorecardConfig


class GenericType(SegmentType):
    type_id = "generic"
    display_name = "Generic"
    Config = None


SEGMENT_TYPES: Dict[str, SegmentType] = {
    t.type_id: t for t in [GenericType(), HeadlinesType(), CoreValuesType(), RocksType(), ScorecardType()]
}


def get_segment_type(type_id: str) -> SegmentType:
    return SEGMENT_TYPES.get(type_id, SEGMENT_TYPES["generic"])


def all_segment_types() -> List[SegmentType]:
    return list(SEGMENT_TYPES.values())
