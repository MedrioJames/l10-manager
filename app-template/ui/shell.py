"""The app's navigation shell: a sidebar plus a content area where screens
are built. Screens are plain functions - build(ctx, **kwargs) - registered
in a dict, not classes, since each one just needs to draw itself into
ctx.content and can recompute anything it needs from ctx.config on the way.
"""

import webbrowser

import tkinter as tk
from tkinter import ttk

import config as cfgmod
import updater
from ui import theme

# A "group" entry renders as a small uppercase label rather than a nav
# button (see _build_layout) - purely cosmetic grouping of the same flat
# screen_key -> builder dispatch, not phase-gating. Issues deliberately
# stays always-reachable rather than hidden behind a phase, since it's
# referenced live during both Prep and Run. Scorecard/Rocks are hidden for
# now (not built yet - see ui/placeholders.py, whose functions are left in
# place, just unwired here, so re-adding them later is a two-line change).
NAV_ITEMS = [
    ("group", "MEETINGS"),
    ("dashboard", "Dashboard"),
    ("prep", "Prep"),
    ("run_meeting", "Run Meeting"),
    ("group", "TEAM DATA"),
    ("issues", "Issues"),
    ("group", "REVIEW"),
    ("review", "Review"),
    ("group", "SETUP"),
    ("schedule_builder", "Schedules"),
    ("settings", "Settings"),
]

# Screens reached by clicking into something rather than the sidebar (a
# specific occurrence's Schedule Editor; "prep" itself is now also a direct
# NAV_ITEMS entry, but stays listed here too since it's still commonly
# reached contextually from Dashboard's occurrence rows) - not part of
# NAV_ITEMS, but still valid navigate() targets.
CONTEXTUAL_SCREENS = ("prep", "schedule_editor")


class AppContext:
    def __init__(self, root: tk.Tk, config: cfgmod.MeetingConfig):
        self.root = root
        self.config = config
        self.content = None
        self._navigate_callback = None
        # A live meeting run, if one is active - in-memory only (see
        # run_state.py). None means no meeting is currently running. Lives
        # here (not on any screen) because AppContext is the one object
        # every screen receives that survives navigate()'s teardown of
        # ctx.content, which is what lets the run's timer keep ticking no
        # matter what screen the user is looking at.
        self.run_state = None
        self.run_indicator = None
        self.presentation_window = None
        # A slot (packed above ctx.content, collapsed/empty by default) that
        # ui/run_indicator.py mounts its bar into - see that module's
        # docstring for why this replaced an earlier place()-overlay
        # approach that covered content instead of pushing it down.
        self.indicator_slot = None
        # The screen currently shown in ctx.content - lets a persistent
        # widget outside the normal screen lifecycle (ui/run_indicator.py's
        # bar) know what's on screen right now without its own navigation
        # tracking. _screen_change_listeners fire right after a screen
        # finishes building, so run_indicator.py can hide its "Back to
        # Run" button the instant the user navigates TO the Run Meeting
        # screen - this can't wait for run_state's own 1Hz tick, since a
        # PAUSED run never ticks and the stale button would sit there
        # showing on the very screen it's meant to link away from.
        self.current_screen_key = None
        self._screen_change_listeners = []

    def add_screen_change_listener(self, callback) -> None:
        self._screen_change_listeners.append(callback)

    def remove_screen_change_listener(self, callback) -> None:
        if callback in self._screen_change_listeners:
            self._screen_change_listeners.remove(callback)

    def _notify_screen_change(self) -> None:
        for callback in list(self._screen_change_listeners):
            callback()

    def navigate(self, screen_key: str, **kwargs) -> None:
        self._navigate_callback(screen_key, **kwargs)

    def reload_config(self) -> None:
        self.config = cfgmod.load_config()

    def save_config(self) -> None:
        cfgmod.save_config(self.config)


class AppShell:
    def __init__(self, root: tk.Tk, config: cfgmod.MeetingConfig, screen_registry: dict, start_screen: str = "dashboard"):
        self.root = root
        self.ctx = AppContext(root, config)
        self.ctx._navigate_callback = self.navigate
        self.screen_registry = screen_registry
        self.nav_buttons = {}
        self._current_screen_key = None
        self._build_layout()
        self.navigate(start_screen)

    def _build_layout(self) -> None:
        container = tk.Frame(self.root, background=theme.BG)
        container.pack(fill="both", expand=True)

        sidebar = tk.Frame(container, background=theme.SIDEBAR_BG, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="L10 Manager", background=theme.SIDEBAR_BG, foreground="white",
            font=("Segoe UI", 12, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 12))

        is_first_group = True
        for key, label in NAV_ITEMS:
            if key == "group":
                if not is_first_group:
                    tk.Frame(sidebar, background=theme.SIDEBAR_HOVER, height=1).pack(fill="x", padx=16, pady=(10, 0))
                is_first_group = False
                # Deliberately lighter weight than the nav links below it
                # (regular, not bold, smaller) plus the divider above - two
                # non-clickable section labels shouldn't compete visually
                # with the actual clickable nav items.
                tk.Label(
                    sidebar, text=label, anchor="w", background=theme.SIDEBAR_BG,
                    foreground=theme.ON_PRIMARY_DARK_MUTED, font=("Segoe UI", 9), padx=16,
                ).pack(fill="x", pady=(10, 2))
                continue

            btn = tk.Button(
                sidebar, text=label, anchor="w", relief="flat", bd=0,
                background=theme.SIDEBAR_BG, foreground="white",
                activebackground=theme.SIDEBAR_ACTIVE, activeforeground="white",
                font=("Segoe UI", 10), padx=16, pady=10, cursor="hand2",
                command=lambda k=key: self.navigate(k),
            )
            btn.pack(fill="x")
            btn.bind("<Enter>", lambda _e, k=key: self._on_nav_hover(k, True))
            btn.bind("<Leave>", lambda _e, k=key: self._on_nav_hover(k, False))
            self.nav_buttons[key] = btn

        footer = tk.Frame(sidebar, background=theme.SIDEBAR_BG)
        footer.pack(side="bottom", fill="x", padx=16, pady=14)
        tk.Label(
            footer, text=f"version {updater.local_version()}", background=theme.SIDEBAR_BG,
            foreground=theme.ON_PRIMARY_DARK_MUTED, font=("Segoe UI", 9),
        ).pack(anchor="w")
        github_link = tk.Label(
            footer, text="GitHub", background=theme.SIDEBAR_BG, foreground="white",
            font=("Segoe UI", 9, "underline"), cursor="hand2",
        )
        github_link.pack(anchor="w", pady=(2, 0))
        github_link.bind("<Button-1>", lambda _event: webbrowser.open(updater.GITHUB_URL))

        right_column = tk.Frame(container, background=theme.BG)
        right_column.pack(side="left", fill="both", expand=True)

        # Collapsed/empty by default - ui/run_indicator.py packs its bar
        # into this (fill="x") when a meeting is running, and unpacks it
        # when the run ends. Packed above content so it pushes content
        # down instead of overlapping it.
        self.indicator_slot = tk.Frame(right_column, background=theme.BG)
        self.indicator_slot.pack(side="top", fill="x")
        self.ctx.indicator_slot = self.indicator_slot

        self.content = tk.Frame(right_column, background=theme.BG)
        self.content.pack(side="top", fill="both", expand=True)
        self.ctx.content = self.content

    def _on_nav_hover(self, key: str, entering: bool) -> None:
        if key == self._current_screen_key:
            return
        self.nav_buttons[key].configure(background=theme.SIDEBAR_HOVER if entering else theme.SIDEBAR_BG)

    def navigate(self, screen_key: str, **kwargs) -> None:
        for child in self.content.winfo_children():
            child.destroy()

        self._current_screen_key = screen_key
        self.ctx.current_screen_key = screen_key
        for key, btn in self.nav_buttons.items():
            btn.configure(background=theme.SIDEBAR_ACTIVE if key == screen_key else theme.SIDEBAR_BG)

        builder = self.screen_registry.get(screen_key)
        if builder is None:
            tk.Label(
                self.content, text=f"Unknown screen: {screen_key}",
                background=theme.BG, foreground=theme.INK,
            ).pack(padx=20, pady=20)
            self.ctx._notify_screen_change()
            return
        builder(self.ctx, **kwargs)
        self.ctx._notify_screen_change()
