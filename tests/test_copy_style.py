"""User-facing strings must not contain em-dashes (house style)."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "faraday"
CHECKED = [*sorted((ROOT / "qt").rglob("*.py")), ROOT / "access_log.py", ROOT / "models" / "schema.py",
           ROOT / "threat_model.py"]


def test_no_em_dashes_in_ui_strings():
    offenders = []
    for path in CHECKED:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
                      and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                if "—" in node.value:
                    offenders.append(f"{path.relative_to(ROOT.parent)}:{node.lineno}")
    assert not offenders, "Em-dash in user-facing strings: " + ", ".join(offenders)
