#!/usr/bin/env python
"""Release guard — run before every ship. No bench/site needed.

Catches the class of outage where the POS looks fine but whole screens are dead:

  1. A frontend `call('lumenpos.api.x.y')` that points at a function which
     doesn't exist, or exists but is NOT whitelisted -> that screen 404s live.
  2. A PRIVATE helper (leading underscore) carrying @frappe.whitelist() ->
     silently published as a public endpoint.
  3. A helper defined BETWEEN @frappe.whitelist() and its function, which steals
     the decorator: the real endpoint stops being callable and the helper
     becomes public. (This took History + Customers down in VPOS 0.64.1.)
  4. Keyword arguments that don't exist on the function being called (an AST
     arity/keyword sweep). This is what broke History in VPOS 0.50.1.

Usage:  python scripts/check_endpoints.py        (exit 1 on any finding)
"""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "lumenpos"
FRONTEND = ROOT / "frontend" / "src"

problems = []


def _decorators(node):
    return [ast.unparse(d) for d in node.decorator_list]


# ---------------------------------------------------------------------------
# Collect every python function: whitelist status, args, and decorator theft
# ---------------------------------------------------------------------------
whitelisted = set()      # "lumenpos.api.sales.submit_sale"
defined = set()
defs_by_name = {}        # name -> [(argnames, has_kwargs)]

for path in APP.rglob("*.py"):
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except SyntaxError as exc:
        problems.append(f"SYNTAX ERROR  {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
        continue

    dotted = ".".join(path.relative_to(ROOT).with_suffix("").parts)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        a = node.args
        names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
        defs_by_name.setdefault(node.name, []).append((names, a.kwarg is not None))

        decs = _decorators(node)
        is_wl = any("whitelist" in d for d in decs)
        defined.add(f"{dotted}.{node.name}")
        if is_wl:
            whitelisted.add(f"{dotted}.{node.name}")
            if node.name.startswith("_"):
                problems.append(
                    f"PRIVATE HELPER IS PUBLIC  {path.relative_to(ROOT)}:{node.lineno} "
                    f"-> {node.name}() carries @frappe.whitelist()"
                )

    # Decorator theft: a def whose decorator line is separated from it by
    # another def/assignment is caught by comparing source order.
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if "@frappe.whitelist" not in line:
            continue
        for j in range(i + 1, min(i + 40, len(lines))):
            nxt = lines[j].strip()
            if not nxt or nxt.startswith("#") or nxt.startswith("@"):
                continue
            if nxt.startswith(("def ", "async def ")):
                name = nxt.split("(")[0].replace("async def ", "").replace("def ", "").strip()
                if name.startswith("_"):
                    problems.append(
                        f"DECORATOR THEFT  {path.relative_to(ROOT)}:{j + 1} "
                        f"-> @frappe.whitelist() lands on private {name}()"
                    )
            break


# ---------------------------------------------------------------------------
# Every frontend call('lumenpos...') must hit a whitelisted function
# ---------------------------------------------------------------------------
CALL_RE = re.compile(r"""call\(\s*['"](lumenpos\.[A-Za-z0-9_.]+)['"]""")

if FRONTEND.exists():
    for path in list(FRONTEND.rglob("*.vue")) + list(FRONTEND.rglob("*.js")):
        text = path.read_text(encoding="utf-8-sig")
        for line_no, line in enumerate(text.splitlines(), 1):
            for endpoint in CALL_RE.findall(line):
                if endpoint in whitelisted:
                    continue
                why = "not whitelisted" if endpoint in defined else "does not exist"
                problems.append(
                    f"DEAD ENDPOINT  {path.relative_to(ROOT)}:{line_no} -> {endpoint} ({why})"
                )


# ---------------------------------------------------------------------------
# Keyword-argument sweep: every kwarg must exist on the target signature
# ---------------------------------------------------------------------------
for path in APP.rglob("*.py"):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
        kwargs = [k.arg for k in node.keywords if k.arg]
        if not name or not kwargs or name not in defs_by_name:
            continue
        if not any(
            has_kwargs or all(k in argnames for k in kwargs)
            for argnames, has_kwargs in defs_by_name[name]
        ):
            problems.append(
                f"BAD KEYWORD  {path.relative_to(ROOT)}:{node.lineno} "
                f"-> {name}({', '.join(k + '=' for k in kwargs)})"
            )


if problems:
    print("\n".join(sorted(set(problems))))
    print(f"\n{len(set(problems))} problem(s) found.")
    sys.exit(1)

print(f"CLEAN — {len(whitelisted)} whitelisted endpoints, all frontend calls resolve.")
