"""Static checks on the Dataform project that do not need Node or BigQuery."""

import re
from pathlib import Path

DEFS = Path(__file__).resolve().parents[2] / "dataform" / "definitions"
REF = re.compile(r'\$\{ref\("([a-zA-Z0-9_]+)"\)\}')
NAME = re.compile(r'name:\s*"([a-zA-Z0-9_]+)"')


def _actions():
    actions = {}
    for f in DEFS.rglob("*.sqlx"):
        text = f.read_text()
        m = NAME.search(text.split("}")[0])
        actions[m.group(1) if m else f.stem] = f
    return actions


def test_every_ref_resolves():
    actions = _actions()
    missing = []
    for name, f in actions.items():
        for r in REF.findall(f.read_text()):
            if r not in actions:
                missing.append((name, r))
    assert not missing, missing


def test_no_dependency_cycles():
    actions = _actions()
    deps = {n: set(REF.findall(f.read_text())) for n, f in actions.items()}
    visiting, done = set(), set()

    def visit(n):
        assert n not in visiting, f"cycle through {n}"
        if n in done:
            return
        visiting.add(n)
        for d in deps[n]:
            visit(d)
        visiting.discard(n)
        done.add(n)

    for n in deps:
        visit(n)


def test_non_declaration_tables_have_assertions():
    for name, f in _actions().items():
        text = f.read_text()
        if 'type: "declaration"' in text or 'type: "view"' in text:
            continue
        assert "assertions" in text, f"{name} has no data quality assertions"
