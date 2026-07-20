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
# screen_key -> builder dispatch, not phase-gating. Scorecard/Rocks/Issues
# deliberately stay always-reachable rather than hidden behind a phase,
# since they're referenced live during both Prep and Run.
NAV_ITEMS = [
    ("group", "MEETINGS"),
    ("dashboard", "Dashboard"),
    ("run_meeting", "Run Meeting"),
    ("group", "TEAM DATA"),
    ("scorecard", "Scorecard"),
    ("rocks", "Rocks"),
    ("issues", "Issues"),
    ("group", "REVIEW"),
    ("conclude", "Conclude"),
    ("group", "SETUP"),
    ("schedule_templates", "Schedules"),
    ("settings", "Settings"),
]

# Screens reached by clicking into something on the Dashboard rather than
# the sidebar (a specific occurrence's Prep/Schedule Editor) - not part of
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
        ).pack(fill="x", padx=16, pady=(18, 14))

        for key, label in NAV_ITEMS:
            if key == "group":
                tk.Label(
                    sidebar, text=label, anchor="w", background=theme.SIDEBAR_BG,
                    foreground="#7FA0B8", font=("Segoe UI", 8, "bold"), padx=16,
                ).pack(fill="x", pady=(14, 2))
                continue

            btn = tk.Button(
                sidebar, text=label, anchor="w", relief="flat", bd=0,
                background=theme.SIDEBAR_BG, foreground="white",
                activebackground=theme.SIDEBAR_ACTIVE, activeforeground="white",
                font=("Segoe UI", 10), padx=16, pady=10, cursor="hand2",
                command=lambda k=key: self.navigate(k),
            )
            btn.pack(fill="x")
            self.nav_buttons[key] = btn

        footer = tk.Frame(sidebar, background=theme.SIDEBAR_BG)
        footer.pack(side="bottom", fill="x", padx=16, pady=14)
        tk.Label(
            footer, text=f"version {updater.local_version()}", background=theme.SIDEBAR_BG,
            foreground="#A9C2D6", font=("Segoe UI", 8),
        ).pack(anchor="w")
        github_link = tk.Label(
            footer, text="GitHub", background=theme.SIDEBAR_BG, foreground="white",
            font=("Segoe UI", 8, "underline"), cursor="hand2",
        )
        github_link.pack(anchor="w", pady=(2, 0))
        github_link.bind("<Button-1>", lambda _event: webbrowser.open(updater.GITHUB_URL))

        self.content = tk.Frame(container, background=theme.BG)
        self.content.pack(side="left", fill="both", expand=True)
        self.ctx.content = self.content

    def navigate(self, screen_key: str, **kwargs) -> None:
        for child in self.content.winfo_children():
            child.destroy()

        for key, btn in self.nav_buttons.items():
            btn.configure(background=theme.SIDEBAR_ACTIVE if key == screen_key else theme.SIDEBAR_BG)

        builder = self.screen_registry.get(screen_key)
        if builder is None:
            tk.Label(
                self.content, text=f"Unknown screen: {screen_key}",
                background=theme.BG, foreground=theme.INK,
            ).pack(padx=20, pady=20)
            return
        builder(self.ctx, **kwargs)
