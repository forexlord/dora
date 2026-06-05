"""Small always-on-top status window (Siri-like) for non-technical users."""

from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont
from collections.abc import Callable
from typing import Any

_HEADLINES: dict[str, str] = {
    "starting": "Starting…",
    "waiting_wake": "Ready when you are",
    "listening": "I'm listening",
    "thinking": "Working on that…",
    "speaking": "Playing my reply",
    "confirm": "I need a quick OK",
    "session_idle": "Still here",
    "text_mode": "Type your command",
}

_DEFAULT_SUBS: dict[str, str] = {
    "starting": "Checking speech, mic, and AI — please wait.",
    "listening": "Speak clearly — I'm ready.",
    "thinking": "Hang on — processing your words…",
    "speaking": "You'll hear this in a moment.",
    "confirm": "Say yes or confirm out loud.",
    "session_idle": "Say your wake phrase when you need me again.",
    "text_mode": "Use the terminal window below.",
}


_HIDE_WINDOW = object()
_SHOW_WINDOW = object()
_USER_DISMISS = object()


class NullStatusOverlay:
    """No-op when overlay is disabled or Tk is unavailable."""

    def start(self, *, begin_hidden: bool = False) -> bool:
        return False

    def set_phase(self, phase: str, subtitle: str | None = None) -> None:
        pass

    def hide(self) -> None:
        pass

    def show(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    @property
    def active(self) -> bool:
        return False


class StatusOverlay:
    """
    Bottom-centered floating card with short status text and a soft pulse
    while listening or thinking. Tk runs on a daemon thread; updates are queued
    from Dora's main thread.
    """

    _SHUTDOWN = object()

    def __init__(
        self,
        wake_hint: str,
        *,
        on_user_dismiss: Callable[[], None] | None = None,
    ) -> None:
        self._wake_hint = (wake_hint or "Say the wake phrase when you need me.").strip()
        self._on_user_dismiss = on_user_dismiss
        self._q: queue.Queue[tuple[str, str | None] | Any] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._started = False
        self._begin_hidden = False

    def start(self, *, begin_hidden: bool = False) -> bool:
        if self._started:
            return True
        self._begin_hidden = begin_hidden
        self._started = True
        self._thread = threading.Thread(target=self._tk_main, name="status-overlay", daemon=True)
        self._thread.start()
        return True

    def set_phase(self, phase: str, subtitle: str | None = None) -> None:
        if not self._started:
            return
        self._q.put((phase, subtitle))

    def hide(self) -> None:
        if not self._started:
            return
        self._q.put(_HIDE_WINDOW)

    def show(self) -> None:
        if not self._started:
            return
        self._q.put(_SHOW_WINDOW)

    def shutdown(self) -> None:
        if not self._started:
            return
        self._q.put(self._SHUTDOWN)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._thread = None
        self._started = False

    @property
    def active(self) -> bool:
        return self._started

    def _resolve_text(self, phase: str, subtitle: str | None) -> tuple[str, str]:
        headline = _HEADLINES.get(phase, "Dora")
        if phase == "waiting_wake":
            default_sub = self._wake_hint
        else:
            default_sub = _DEFAULT_SUBS.get(phase, "")
        sub = default_sub if subtitle is None else subtitle
        return headline, sub

    def _tk_main(self) -> None:
        try:
            root = tk.Tk()
        except Exception:
            self._started = False
            return

        root.title("Dora")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", 0.94)
        except tk.TclError:
            pass

        w, h = 440, 140
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(40, sh - h - 72)
        root.geometry(f"{w}x{h}+{x}+{y}")

        bg = "#1c1c1e"
        accent_listen = "#30d158"
        accent_think = "#5ac8fa"

        outer = tk.Frame(root, bg=bg, padx=18, pady=14)
        outer.pack(fill=tk.BOTH, expand=True)

        try:
            brand_font = tkfont.Font(family="Segoe UI", size=9, weight="normal")
            main_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
            sub_font = tkfont.Font(family="Segoe UI", size=11)
        except tk.TclError:
            brand_font = tkfont.Font(size=9)
            main_font = tkfont.Font(size=16, weight="bold")
            sub_font = tkfont.Font(size=11)

        canvas = tk.Canvas(
            outer,
            width=28,
            height=28,
            bg=bg,
            highlightthickness=0,
        )
        canvas.pack(side=tk.LEFT, padx=(0, 12))

        text_col = tk.Frame(outer, bg=bg)
        text_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header = tk.Frame(text_col, bg=bg)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="DORA",
            fg="#636366",
            bg=bg,
            font=brand_font,
            anchor="w",
        ).pack(side=tk.LEFT)

        def _request_dismiss(_event: object | None = None) -> None:
            self._q.put(_USER_DISMISS)

        close_btn = tk.Label(
            header,
            text="\u00d7",
            fg="#8e8e93",
            bg=bg,
            font=tkfont.Font(family="Segoe UI", size=14),
            cursor="hand2",
            padx=6,
            pady=0,
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", _request_dismiss)
        close_btn.bind("<Enter>", lambda _e: close_btn.config(fg="#ffffff"))
        close_btn.bind("<Leave>", lambda _e: close_btn.config(fg="#8e8e93"))

        lbl_main = tk.Label(
            text_col,
            text="",
            fg="#ffffff",
            bg=bg,
            font=main_font,
            anchor="w",
            wraplength=w - 88,
            justify=tk.LEFT,
        )
        lbl_main.pack(fill=tk.X, pady=(4, 0))
        lbl_sub = tk.Label(
            text_col,
            text="",
            fg="#aeaeb2",
            bg=bg,
            font=sub_font,
            anchor="w",
            wraplength=w - 88,
            justify=tk.LEFT,
        )
        lbl_sub.pack(fill=tk.X, pady=(6, 0))

        state: dict[str, Any] = {
            "phase": "starting",
            "pulse": 0.0,
            "oval": canvas.create_oval(4, 4, 24, 24, fill=accent_listen, outline=""),
        }

        def apply_phase(phase: str, subtitle: str | None) -> None:
            state["phase"] = phase
            headline, sub = self._resolve_text(phase, subtitle)
            lbl_main.config(text=headline)
            lbl_sub.config(text=sub)

        apply_phase("starting", None)

        state["visible"] = not getattr(self, "_begin_hidden", False)
        if getattr(self, "_begin_hidden", False):
            root.withdraw()

        def pump() -> None:
            drained = False
            while True:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                drained = True
                if item is self._SHUTDOWN:
                    root.destroy()
                    return
                if item is _HIDE_WINDOW:
                    state["visible"] = False
                    root.withdraw()
                    continue
                if item is _SHOW_WINDOW:
                    state["visible"] = True
                    root.deiconify()
                    try:
                        root.attributes("-topmost", True)
                    except tk.TclError:
                        pass
                    root.lift()
                    continue
                if item is _USER_DISMISS:
                    state["visible"] = False
                    root.withdraw()
                    dismiss = self._on_user_dismiss
                    if dismiss is not None:
                        try:
                            dismiss()
                        except Exception:
                            pass
                    continue
                if isinstance(item, tuple) and len(item) == 2:
                    apply_phase(str(item[0]), item[1])

            phase = state["phase"]
            visible = state.get("visible", True)
            if visible:
                state["pulse"] = state["pulse"] + 0.22
                t = state["pulse"]
                r_base = 10.0
                if phase == "listening":
                    scale = 0.85 + 0.15 * (0.5 + 0.5 * math.sin(t))
                    r = r_base * scale
                    cx, cy = 14.0, 14.0
                    canvas.coords(state["oval"], cx - r, cy - r, cx + r, cy + r)
                    canvas.itemconfig(state["oval"], fill=accent_listen)
                elif phase == "thinking":
                    scale = 0.88 + 0.12 * (0.5 + 0.5 * math.sin(t * 1.4))
                    r = r_base * scale
                    cx, cy = 14.0, 14.0
                    canvas.coords(state["oval"], cx - r, cy - r, cx + r, cy + r)
                    canvas.itemconfig(state["oval"], fill=accent_think)
                elif phase == "speaking":
                    canvas.coords(state["oval"], 5, 5, 23, 23)
                    canvas.itemconfig(state["oval"], fill="#bf5af2")
                else:
                    canvas.coords(state["oval"], 6, 6, 22, 22)
                    canvas.itemconfig(state["oval"], fill="#48484a")

            fast = visible and (phase in {"listening", "thinking"} or drained)
            root.after(55 if fast else 220, pump)

        root.after(40, pump)
        try:
            root.mainloop()
        finally:
            self._started = False


def build_status_overlay(
    enabled: bool,
    wake_hint: str,
    *,
    on_user_dismiss: Callable[[], None] | None = None,
) -> StatusOverlay | NullStatusOverlay:
    if not enabled:
        return NullStatusOverlay()
    try:
        import tkinter  # noqa: F401, PLC0415
    except ImportError:
        return NullStatusOverlay()
    return StatusOverlay(wake_hint=wake_hint, on_user_dismiss=on_user_dismiss)
