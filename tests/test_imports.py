"""Every relative import in lumen/ resolves, including those inside functions, which only fail
when that code runs. Guards against breakage when code moves."""

import ast
import importlib
import importlib.util
from pathlib import Path

PACKAGE = Path(__file__).parent.parent / "lumen"


def test_all_relative_imports_resolve(env):
    broken = []
    for f in PACKAGE.rglob("*.py"):
        parts = f.relative_to(PACKAGE.parent).with_suffix("").parts
        pkg = list(parts if f.name == "__init__.py" else parts[:-1])
        if f.name == "__init__.py":
            pkg = pkg[:-1]
        for node in ast.walk(ast.parse(f.read_text())):
            if not (isinstance(node, ast.ImportFrom) and node.level):
                continue
            base = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
            mod = ".".join(base + ([node.module] if node.module else []))
            if importlib.util.find_spec(mod) is None:
                broken.append(f"{f.name}:{node.lineno} no module {mod}")
                continue
            m = importlib.import_module(mod)
            for alias in node.names:
                if not hasattr(m, alias.name) and importlib.util.find_spec(f"{mod}.{alias.name}") is None:
                    broken.append(f"{f.name}:{node.lineno} {mod} has no {alias.name}")
    assert broken == []
