# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""The English texts Frappe and ERPNext already translate, per language, across
the benches given (v13/v14 ship CSV files, v15 CSV and PO, v16 PO). Frappe
merges every app's translations into one table where the app installed last
wins, so a LumenPOS row for one of these would rename that text across the
whole desk; write_csv.mjs leaves them out.

Usage: python3 erp_keys.py <work> <lang>... (BENCHES: space separated bench
folders, default the four LumenPOS test benches)."""

import csv
import io
import json
import os
import re
import sys
from pathlib import Path

WORK, LANGS = sys.argv[1], sys.argv[2:]
BENCHES = os.environ.get(
    "BENCHES",
    "/home/frappe/bench13 /home/frappe/bench14 /home/frappe/bench15 /home/frappe/bench16lp",
).split()


ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def unquote(text):
    """The text between the outer quotes of a PO line, escapes kept."""
    text = text.strip()
    return text[1:-1] if len(text) >= 2 and text[0] == '"' and text[-1] == '"' else text


def unescape(text):
    return re.sub(r"\\(.)", lambda m: ESCAPES.get(m.group(1), m.group(0)), text)


def po_keys(path):
    """msgid (with ':context' when it has one) of every translated entry."""
    keys = set()
    entry = {"ctx": None, "id": None, "str": None}
    part = None

    def flush():
        if entry["id"] is not None and entry["str"] is not None:
            msgid, msgstr = "".join(entry["id"]), "".join(entry["str"])
            if msgid and msgstr:
                ctx = unescape(entry["ctx"]) if entry["ctx"] else ""
                keys.add(unescape(msgid) + (":" + ctx if ctx else ""))
        entry.update(ctx=None, id=None, str=None)

    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("msgctxt "):
            flush()
            entry["ctx"], part = unquote(line[8:]), "ctx"
        elif line.startswith("msgid "):
            if part != "ctx":
                flush()
            entry["id"], part = [unquote(line[6:])], "id"
        elif line.startswith("msgstr "):
            entry["str"], part = [unquote(line[7:])], "str"
        elif line.startswith('"') and part in ("id", "str"):
            entry[part].append(unquote(line))
    flush()
    return keys


def csv_keys(path):
    keys = set()
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for row in csv.reader(io.StringIO(text, newline="")):
        if len(row) >= 2 and row[0] and row[1].strip():
            keys.add(row[0] + (":" + row[2] if len(row) > 2 and row[2] else ""))
    return keys


for lang in LANGS:
    found = set()
    for bench in BENCHES:
        for app in ("frappe", "erpnext"):
            base = f"{bench}/apps/{app}/{app}"
            if os.path.exists(f"{base}/translations/{lang}.csv"):
                found |= csv_keys(f"{base}/translations/{lang}.csv")
            if os.path.exists(f"{base}/locale/{lang.replace('-', '_')}.po"):
                found |= po_keys(f"{base}/locale/{lang.replace('-', '_')}.po")
    Path(f"{WORK}/erp_keys_{lang}.json").write_text(json.dumps(sorted(found), ensure_ascii=False), encoding="utf-8")
    print(lang, len(found))
