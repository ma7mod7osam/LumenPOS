#!/usr/bin/env python
"""Unit test for the shift-schedule matcher — runs WITHOUT a bench or a site.

It stubs `frappe` and executes only the two pure helpers out of register.py, so
the overnight-shift arithmetic stays covered without needing a database.

The cases that matter: a shift whose end time is at or before its start crosses
midnight, so a 22:00->06:00 shift opened at 23:40 belongs to the PREVIOUS day's
window, and one opened at 01:15 belongs to the same window from the day before.
Getting that wrong means either alerting on every night shift or never alerting.

Usage: python scripts/test_shift_schedule.py   (exit 1 on failure)
"""

import ast
import datetime
import io
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "lumenpos" / "api" / "register.py"

WANTED = {"_as_time", "_scheduled_end"}
SLOTS = []


class Row(dict):
    __getattr__ = dict.get


def _load():
    tree = ast.parse(io.open(SRC, encoding="utf-8").read())
    fake = types.ModuleType("frappe")
    fake.get_all = lambda *a, **k: list(SLOTS)
    ns = {
        "frappe": fake,
        "DAY_NAMES": [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        ],
    }
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANTED:
            exec(compile(ast.Module([node], []), "<f>", "exec"), ns)
            found.add(node.name)
    missing = WANTED - found
    if missing:
        raise SystemExit(f"helpers not found in register.py: {sorted(missing)}")
    return ns["_scheduled_end"]


def main():
    scheduled_end = _load()

    def D(s):
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M")

    failures = 0

    def check(label, slots, opened, expect):
        nonlocal failures
        global SLOTS
        SLOTS = [Row(day=d, start_time=s, end_time=e) for d, s, e in slots]
        got = scheduled_end("SCHED", D(opened))
        want = D(expect) if expect else None
        if got != want:
            failures += 1
            print(f"FAIL {label}: got {got}, want {want}")
        else:
            print(f"ok   {label} -> {got}")

    # 2026-08-13 is a Thursday.
    check("morning shift", [("Every Day", "08:00:00", "16:00:00")],
          "2026-08-13 08:05", "2026-08-13 16:00")
    check("overnight, opened before midnight", [("Every Day", "22:00:00", "06:00:00")],
          "2026-08-13 23:40", "2026-08-14 06:00")
    check("overnight, opened after midnight", [("Every Day", "22:00:00", "06:00:00")],
          "2026-08-14 01:15", "2026-08-14 06:00")
    check("early open (before start)", [("Every Day", "08:00:00", "16:00:00")],
          "2026-08-13 07:50", "2026-08-13 16:00")
    check("day-specific match (Thursday)", [("Thursday", "09:00:00", "17:00:00")],
          "2026-08-13 09:30", "2026-08-13 17:00")
    check("day-specific non-match (Monday only)", [("Monday", "09:00:00", "17:00:00")],
          "2026-08-13 09:30", None)
    check("no slots -> caller uses the fallback hours", [], "2026-08-13 09:30", None)

    print("\n" + ("ALL PASS" if not failures else f"{failures} FAILURE(S)"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
