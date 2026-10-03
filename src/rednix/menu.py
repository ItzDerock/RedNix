"""Small searchable terminal picker, using only the standard library."""

from __future__ import annotations

import sys

from .state import StateError


def matching(labels: list[str], query: str) -> list[int]:
    words = query.casefold().split()
    return [i for i, label in enumerate(labels)
            if all(word in label.casefold() for word in words)]


def choose(title: str, labels: list[str]) -> int | None:
    if not labels:
        raise StateError("nothing available to select")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise StateError("the menu needs a terminal; use --list or specify a name")
    try:
        import curses
    except ImportError:
        return _numbered(title, labels)
    try:
        return curses.wrapper(_screen, title, labels)
    except curses.error:
        return _numbered(title, labels)


def _numbered(title: str, labels: list[str]) -> int | None:
    print(title)
    for i, label in enumerate(labels, 1):
        print(f"  {i:>2}. {label}")
    while True:
        try:
            answer = input("Number (Enter to cancel): ").strip()
        except EOFError:
            return None
        if not answer:
            return None
        if answer.isdecimal() and 1 <= int(answer) <= len(labels):
            return int(answer) - 1
        print(f"Enter a number from 1 to {len(labels)}.")


def _screen(screen, title: str, labels: list[str]) -> int | None:
    import curses

    query = ""
    selected = 0
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    while True:
        matches = matching(labels, query)
        selected = min(selected, max(0, len(matches) - 1))
        screen.erase()
        height, width = screen.getmaxyx()

        def line(row, value, style=0):
            if 0 <= row < height and width > 1:
                # Avoid control characters from desktop entry names.
                value = "".join(c if c.isprintable() else " " for c in value)
                try:
                    screen.addnstr(row, 0, value, width - 1, style)
                except curses.error:
                    pass

        line(0, title, curses.A_BOLD)
        line(1, "Type to search • ↑/↓ select • Enter launch • Esc cancel")
        line(2, f"Search: {query}")
        visible = max(1, height - 5)
        first = max(0, selected - visible + 1)
        for row, position in enumerate(range(first, min(len(matches), first + visible)), 4):
            active = position == selected
            line(row, ("> " if active else "  ") + labels[matches[position]],
                 curses.A_REVERSE if active else 0)
        if not matches:
            line(4, "No matches")
        screen.refresh()
        key = screen.get_wch()
        if key in ("\x1b", "\x03"):
            return None
        if key in ("\n", "\r", curses.KEY_ENTER) and matches:
            return matches[selected]
        if key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN:
            selected = min(max(0, len(matches) - 1), selected + 1)
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            query = query[:-1]
            selected = 0
        elif key == "\x15":
            query = ""
            selected = 0
        elif isinstance(key, str) and key.isprintable():
            query += key
            selected = 0
