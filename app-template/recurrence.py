"""Recurrence rules for repeating L10 instances.

A small, stdlib-only recurrence engine inspired by Google Calendar's custom
recurrence options: daily/weekly/monthly/yearly, an interval ("every N"),
specific weekdays for weekly, "day N of the month" or "the Nth <weekday> of
the month" for monthly, and never/on-date/after-N-occurrences end
conditions.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

FREQ_DAILY = "daily"
FREQ_WEEKLY = "weekly"
FREQ_MONTHLY = "monthly"
FREQ_YEARLY = "yearly"
FREQUENCIES = (FREQ_DAILY, FREQ_WEEKLY, FREQ_MONTHLY, FREQ_YEARLY)

MONTHLY_BY_DAY_OF_MONTH = "day_of_month"
MONTHLY_BY_WEEKDAY = "nth_weekday"

END_NEVER = "never"
END_ON_DATE = "on_date"
END_AFTER_COUNT = "after_count"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NTH_NAMES = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", -1: "last"}

MAX_ITERATIONS = 2000  # safety cap; end conditions should stop well before this


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> Optional[date]:
    """weekday: 0=Monday..6=Sunday. n: 1-4 for the nth occurrence, -1 for the last."""
    cal = calendar.Calendar()
    matches = [d for d in cal.itermonthdates(year, month) if d.month == month and d.weekday() == weekday]
    if not matches:
        return None
    if n == -1:
        return matches[-1]
    if 1 <= n <= len(matches):
        return matches[n - 1]
    return None


@dataclass
class RecurrenceRule:
    frequency: str = FREQ_WEEKLY
    interval: int = 1
    start_date: date = field(default_factory=date.today)
    by_weekday: List[int] = field(default_factory=list)  # 0=Monday..6=Sunday
    monthly_mode: str = MONTHLY_BY_DAY_OF_MONTH
    day_of_month: Optional[int] = None
    nth_week: int = 1  # 1-4, or -1 for "last" (used with monthly_mode == MONTHLY_BY_WEEKDAY)
    end_type: str = END_NEVER
    end_date: Optional[date] = None
    end_count: Optional[int] = None

    def __post_init__(self):
        if self.frequency == FREQ_WEEKLY and not self.by_weekday:
            self.by_weekday = [self.start_date.weekday()]
        if self.frequency == FREQ_MONTHLY and self.monthly_mode == MONTHLY_BY_DAY_OF_MONTH and self.day_of_month is None:
            self.day_of_month = self.start_date.day
        if self.frequency == FREQ_MONTHLY and self.monthly_mode == MONTHLY_BY_WEEKDAY and not self.by_weekday:
            self.by_weekday = [self.start_date.weekday()]

    def to_dict(self) -> dict:
        return {
            "frequency": self.frequency,
            "interval": self.interval,
            "start_date": self.start_date.isoformat(),
            "by_weekday": list(self.by_weekday),
            "monthly_mode": self.monthly_mode,
            "day_of_month": self.day_of_month,
            "nth_week": self.nth_week,
            "end_type": self.end_type,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "end_count": self.end_count,
        }

    @staticmethod
    def from_dict(d: dict) -> "RecurrenceRule":
        return RecurrenceRule(
            frequency=d.get("frequency", FREQ_WEEKLY),
            interval=int(d.get("interval", 1)),
            start_date=date.fromisoformat(d["start_date"]) if d.get("start_date") else date.today(),
            by_weekday=list(d.get("by_weekday", [])),
            monthly_mode=d.get("monthly_mode", MONTHLY_BY_DAY_OF_MONTH),
            day_of_month=d.get("day_of_month"),
            nth_week=int(d.get("nth_week", 1)),
            end_type=d.get("end_type", END_NEVER),
            end_date=date.fromisoformat(d["end_date"]) if d.get("end_date") else None,
            end_count=d.get("end_count"),
        )

    def describe(self) -> str:
        interval_prefix = "Every" if self.interval == 1 else f"Every {self.interval}"

        if self.frequency == FREQ_DAILY:
            unit = "day" if self.interval == 1 else "days"
            base = f"{interval_prefix} {unit}"
        elif self.frequency == FREQ_WEEKLY:
            unit = "week" if self.interval == 1 else "weeks"
            days = ", ".join(WEEKDAY_ABBR[w] for w in sorted(self.by_weekday))
            base = f"{interval_prefix} {unit} on {days}" if days else f"{interval_prefix} {unit}"
        elif self.frequency == FREQ_MONTHLY:
            unit = "month" if self.interval == 1 else "months"
            if self.monthly_mode == MONTHLY_BY_WEEKDAY:
                nth = NTH_NAMES.get(self.nth_week, f"{self.nth_week}th")
                wd = WEEKDAY_NAMES[self.by_weekday[0]] if self.by_weekday else WEEKDAY_NAMES[self.start_date.weekday()]
                base = f"{interval_prefix} {unit} on the {nth} {wd}"
            else:
                base = f"{interval_prefix} {unit} on day {self.day_of_month}"
        elif self.frequency == FREQ_YEARLY:
            unit = "year" if self.interval == 1 else "years"
            # Manual "Month Day" formatting rather than %-d/%#d - those flags
            # aren't portable (%-d is Unix-only, %#d is Windows-only).
            base = f"{interval_prefix} {unit} on {self.start_date.strftime('%B')} {self.start_date.day}"
        else:
            base = "Custom recurrence"

        if self.end_type == END_ON_DATE and self.end_date:
            base += f", until {self.end_date.isoformat()}"
        elif self.end_type == END_AFTER_COUNT and self.end_count:
            base += f", {self.end_count} times"

        return base


def generate_occurrences(rule: RecurrenceRule, range_start: date, range_end: date) -> List[date]:
    """Returns sorted occurrence dates that fall within [range_start, range_end].

    End conditions (after-N-occurrences, until-date) are evaluated against
    the *full* sequence starting at rule.start_date, not just the dates
    that happen to fall in the requested range.
    """
    if range_end < rule.start_date:
        return []

    results: List[date] = []
    occurrence_index = 0  # 0-based count of ALL occurrences since start_date

    def within_end_conditions(candidate: date) -> bool:
        if rule.end_type == END_ON_DATE and rule.end_date and candidate > rule.end_date:
            return False
        if rule.end_type == END_AFTER_COUNT and rule.end_count and occurrence_index >= rule.end_count:
            return False
        return True

    if rule.frequency == FREQ_DAILY:
        current = rule.start_date
        iterations = 0
        while current <= range_end and iterations < MAX_ITERATIONS:
            iterations += 1
            if not within_end_conditions(current):
                break
            if current >= range_start:
                results.append(current)
            occurrence_index += 1
            current += timedelta(days=max(1, rule.interval))

    elif rule.frequency == FREQ_WEEKLY:
        weekdays = sorted(rule.by_weekday) if rule.by_weekday else [rule.start_date.weekday()]
        week_anchor = rule.start_date - timedelta(days=rule.start_date.weekday())
        week_offset = 0
        iterations = 0
        stop = False
        while not stop and iterations < MAX_ITERATIONS:
            week_start = week_anchor + timedelta(weeks=week_offset)
            if week_start > range_end:
                break
            if week_offset % max(1, rule.interval) == 0:
                for wd in weekdays:
                    iterations += 1
                    candidate = week_start + timedelta(days=wd)
                    if candidate < rule.start_date:
                        continue
                    if candidate > range_end:
                        continue
                    if not within_end_conditions(candidate):
                        stop = True
                        break
                    if candidate >= range_start:
                        results.append(candidate)
                    occurrence_index += 1
            week_offset += 1

    elif rule.frequency == FREQ_MONTHLY:
        month_offset = 0
        iterations = 0
        stop = False
        while not stop and iterations < MAX_ITERATIONS:
            iterations += 1
            base_month = _add_months(rule.start_date, month_offset)
            if base_month > range_end:
                break
            if month_offset % max(1, rule.interval) == 0:
                if rule.monthly_mode == MONTHLY_BY_WEEKDAY:
                    weekday = rule.by_weekday[0] if rule.by_weekday else rule.start_date.weekday()
                    candidate = _nth_weekday_of_month(base_month.year, base_month.month, weekday, rule.nth_week)
                else:
                    day = min(rule.day_of_month or rule.start_date.day, calendar.monthrange(base_month.year, base_month.month)[1])
                    candidate = date(base_month.year, base_month.month, day)

                if candidate and candidate >= rule.start_date:
                    if candidate > range_end:
                        pass
                    elif not within_end_conditions(candidate):
                        stop = True
                    else:
                        if candidate >= range_start:
                            results.append(candidate)
                        occurrence_index += 1
            month_offset += 1

    elif rule.frequency == FREQ_YEARLY:
        year_offset = 0
        iterations = 0
        stop = False
        while not stop and iterations < MAX_ITERATIONS:
            iterations += 1
            candidate = _add_months(rule.start_date, year_offset * 12)
            if candidate > range_end:
                break
            if year_offset % max(1, rule.interval) == 0 and candidate >= rule.start_date:
                if not within_end_conditions(candidate):
                    stop = True
                else:
                    if candidate >= range_start:
                        results.append(candidate)
                    occurrence_index += 1
            year_offset += 1

    return sorted(set(results))
