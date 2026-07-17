"""Dummy screens for the L10 sections we haven't built yet. Real Scorecard,
Rocks, Issues, and Conclude tooling comes in a later phase - these just give
the navigation shell somewhere to point so the overall app shape exists."""

from tkinter import ttk


def _build_placeholder(ctx, title: str, blurb: str) -> None:
    frame = ttk.Frame(ctx.content)
    frame.pack(fill="both", expand=True, padx=32, pady=32)
    ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
    ttk.Label(frame, text=blurb, style="Body.TLabel", wraplength=520, justify="left").pack(anchor="w")
    ttk.Label(frame, text="Coming soon.", style="Muted.TLabel").pack(anchor="w", pady=(16, 0))


def build_scorecard(ctx, **kwargs) -> None:
    _build_placeholder(
        ctx, "Scorecard",
        "This is where your team's weekly measurables will live - a handful of "
        "numbers per person, each simply on-track or off-track.",
    )


def build_rocks(ctx, **kwargs) -> None:
    _build_placeholder(
        ctx, "Rocks",
        "This is where this quarter's Rocks (90-day priorities) will be tracked, "
        "with a quick on-track/off-track status for each.",
    )


def build_issues(ctx, **kwargs) -> None:
    _build_placeholder(
        ctx, "Issues",
        "This is where the Issues List will live, ready for IDS (Identify, "
        "Discuss, Solve) during the meeting.",
    )


def build_conclude(ctx, **kwargs) -> None:
    _build_placeholder(
        ctx, "Conclude",
        "This is where you'll recap new to-dos, decide on any cascading "
        "message, and rate the meeting.",
    )
