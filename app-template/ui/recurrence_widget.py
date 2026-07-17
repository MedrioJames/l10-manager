"""A reusable recurrence-rule editor widget, shared by the setup wizard and
the settings editor - Google-Calendar-style custom recurrence, simplified:
daily/weekly/monthly/yearly, an interval, specific weekdays, "day N" or "the
Nth <weekday>" for monthly, and never/on-date/after-N-occurrences endings.
"""

from datetime import date
import tkinter as tk
from tkinter import ttk

import recurrence as rec
from ui import theme

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_FULL_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NTH_LABELS = ["1st", "2nd", "3rd", "4th", "last"]
NTH_LABEL_TO_VALUE = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "last": -1}
NTH_VALUE_TO_LABEL = {v: k for k, v in NTH_LABEL_TO_VALUE.items()}


class RecurrenceEditor(ttk.Frame):
    def __init__(self, parent, initial_rule: rec.RecurrenceRule = None):
        super().__init__(parent)
        rule = initial_rule or rec.RecurrenceRule(start_date=date.today())

        self.freq_var = tk.StringVar(value=rule.frequency)
        self.interval_var = tk.StringVar(value=str(rule.interval))
        self.weekday_vars = {i: tk.BooleanVar(value=i in rule.by_weekday) for i in range(7)}
        self.monthly_mode_var = tk.StringVar(value=rule.monthly_mode)
        self.day_of_month_var = tk.StringVar(value=str(rule.day_of_month or rule.start_date.day))
        self.nth_week_var = tk.StringVar(value=NTH_VALUE_TO_LABEL.get(rule.nth_week, "1st"))
        self.nth_weekday_var = tk.StringVar(
            value=WEEKDAY_FULL_NAMES[rule.by_weekday[0] if rule.by_weekday else rule.start_date.weekday()]
        )
        self.start_date_var = tk.StringVar(value=rule.start_date.isoformat())
        self.end_type_var = tk.StringVar(value=rule.end_type)
        self.end_date_var = tk.StringVar(value=rule.end_date.isoformat() if rule.end_date else "")
        self.end_count_var = tk.StringVar(value=str(rule.end_count or 5))

        self._build()
        self._on_frequency_changed()

    def _build(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Repeats").pack(side="left", padx=(0, 8))
        freq_combo = ttk.Combobox(
            row, textvariable=self.freq_var, state="readonly", width=12,
            values=[rec.FREQ_DAILY, rec.FREQ_WEEKLY, rec.FREQ_MONTHLY, rec.FREQ_YEARLY],
        )
        freq_combo.pack(side="left")
        freq_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_frequency_changed())

        self.interval_row = ttk.Frame(self)
        self.interval_row.pack(fill="x", pady=(0, 8))
        ttk.Label(self.interval_row, text="Every").pack(side="left", padx=(0, 8))
        ttk.Spinbox(self.interval_row, from_=1, to=99, width=4, textvariable=self.interval_var,
                    command=self._update_preview).pack(side="left")
        self.interval_unit_label = ttk.Label(self.interval_row, text="week(s)")
        self.interval_unit_label.pack(side="left", padx=(6, 0))
        self.interval_var.trace_add("write", lambda *_: self._update_preview())

        self.weekday_frame = ttk.Frame(self)
        ttk.Label(self.weekday_frame, text="Repeat on").pack(side="left", padx=(0, 8))
        for i, label in enumerate(WEEKDAY_LABELS):
            cb = ttk.Checkbutton(self.weekday_frame, text=label, variable=self.weekday_vars[i],
                                  command=self._update_preview)
            cb.pack(side="left", padx=2)

        self.monthly_frame = ttk.Frame(self)
        day_row = ttk.Frame(self.monthly_frame)
        day_row.pack(fill="x", anchor="w")
        ttk.Radiobutton(day_row, text="On day", variable=self.monthly_mode_var,
                         value=rec.MONTHLY_BY_DAY_OF_MONTH, command=self._update_preview).pack(side="left")
        ttk.Spinbox(day_row, from_=1, to=31, width=4, textvariable=self.day_of_month_var,
                    command=self._update_preview).pack(side="left", padx=(4, 0))
        ttk.Label(day_row, text="of the month").pack(side="left", padx=(4, 0))

        weekday_rule_row = ttk.Frame(self.monthly_frame)
        weekday_rule_row.pack(fill="x", anchor="w", pady=(4, 0))
        ttk.Radiobutton(weekday_rule_row, text="On the", variable=self.monthly_mode_var,
                         value=rec.MONTHLY_BY_WEEKDAY, command=self._update_preview).pack(side="left")
        nth_combo = ttk.Combobox(weekday_rule_row, textvariable=self.nth_week_var, state="readonly", width=5,
                                  values=NTH_LABELS)
        nth_combo.pack(side="left", padx=(4, 0))
        nth_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())
        weekday_combo = ttk.Combobox(weekday_rule_row, textvariable=self.nth_weekday_var, state="readonly", width=10,
                                      values=WEEKDAY_FULL_NAMES)
        weekday_combo.pack(side="left", padx=(4, 0))
        weekday_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())

        start_row = ttk.Frame(self)
        start_row.pack(fill="x", pady=(8, 8))
        ttk.Label(start_row, text="Starts (YYYY-MM-DD)").pack(side="left", padx=(0, 8))
        ttk.Entry(start_row, textvariable=self.start_date_var, width=12).pack(side="left")
        self.start_date_var.trace_add("write", lambda *_: self._update_preview())

        end_row = ttk.Frame(self)
        end_row.pack(fill="x", pady=(0, 8))
        ttk.Label(end_row, text="Ends").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(end_row, text="Never", variable=self.end_type_var,
                         value=rec.END_NEVER, command=self._update_preview).pack(side="left")
        ttk.Radiobutton(end_row, text="On", variable=self.end_type_var,
                         value=rec.END_ON_DATE, command=self._update_preview).pack(side="left", padx=(8, 0))
        ttk.Entry(end_row, textvariable=self.end_date_var, width=12).pack(side="left", padx=(4, 0))
        ttk.Radiobutton(end_row, text="After", variable=self.end_type_var,
                         value=rec.END_AFTER_COUNT, command=self._update_preview).pack(side="left", padx=(8, 0))
        ttk.Spinbox(end_row, from_=1, to=999, width=4, textvariable=self.end_count_var,
                    command=self._update_preview).pack(side="left", padx=(4, 0))
        ttk.Label(end_row, text="occurrences").pack(side="left", padx=(4, 0))
        self.end_date_var.trace_add("write", lambda *_: self._update_preview())
        self.end_count_var.trace_add("write", lambda *_: self._update_preview())

        self.preview_label = ttk.Label(self, style="Muted.TLabel", wraplength=440, justify="left")
        self.preview_label.pack(fill="x", anchor="w", pady=(4, 0))

    def _on_frequency_changed(self) -> None:
        freq = self.freq_var.get()
        self.weekday_frame.pack_forget()
        self.monthly_frame.pack_forget()

        unit_map = {
            rec.FREQ_DAILY: "day(s)",
            rec.FREQ_WEEKLY: "week(s)",
            rec.FREQ_MONTHLY: "month(s)",
            rec.FREQ_YEARLY: "year(s)",
        }
        self.interval_unit_label.configure(text=unit_map.get(freq, ""))

        if freq == rec.FREQ_WEEKLY:
            self.weekday_frame.pack(fill="x", pady=(0, 8), after=self.interval_row)
        elif freq == rec.FREQ_MONTHLY:
            self.monthly_frame.pack(fill="x", pady=(0, 8), after=self.interval_row)

        self._update_preview()

    def _update_preview(self) -> None:
        try:
            rule = self.get_rule()
            self.preview_label.configure(text=rule.describe(), foreground=theme.MUTED)
        except ValueError as exc:
            self.preview_label.configure(text=f"({exc})", foreground=theme.DANGER)

    def get_rule(self) -> rec.RecurrenceRule:
        try:
            start = date.fromisoformat(self.start_date_var.get().strip())
        except ValueError:
            raise ValueError("Start date must be in YYYY-MM-DD format")

        try:
            interval = max(1, int(self.interval_var.get()))
        except ValueError:
            interval = 1

        freq = self.freq_var.get()
        by_weekday = [i for i, v in self.weekday_vars.items() if v.get()]

        end_type = self.end_type_var.get()
        end_date_value = None
        end_count_value = None
        if end_type == rec.END_ON_DATE:
            try:
                end_date_value = date.fromisoformat(self.end_date_var.get().strip())
            except ValueError:
                raise ValueError("End date must be in YYYY-MM-DD format")
        elif end_type == rec.END_AFTER_COUNT:
            try:
                end_count_value = max(1, int(self.end_count_var.get()))
            except ValueError:
                end_count_value = 5

        day_of_month = None
        try:
            day_of_month = int(self.day_of_month_var.get())
        except ValueError:
            day_of_month = start.day

        nth_week = NTH_LABEL_TO_VALUE.get(self.nth_week_var.get(), 1)
        try:
            nth_weekday = WEEKDAY_FULL_NAMES.index(self.nth_weekday_var.get())
        except ValueError:
            nth_weekday = start.weekday()

        monthly_weekday = [nth_weekday] if freq == rec.FREQ_MONTHLY and self.monthly_mode_var.get() == rec.MONTHLY_BY_WEEKDAY else by_weekday

        return rec.RecurrenceRule(
            frequency=freq,
            interval=interval,
            start_date=start,
            by_weekday=monthly_weekday if freq == rec.FREQ_MONTHLY else by_weekday,
            monthly_mode=self.monthly_mode_var.get(),
            day_of_month=day_of_month,
            nth_week=nth_week,
            end_type=end_type,
            end_date=end_date_value,
            end_count=end_count_value,
        )
