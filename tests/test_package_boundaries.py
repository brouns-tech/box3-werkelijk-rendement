import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("package", ["models", "calculations", "reconciliation"])
def test_core_modules_do_not_import_infrastructure(package):
    directory = ROOT / "src/wr" / package
    for path in directory.glob("*.py"):
        if path.name == "service.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert not module.startswith(("wr.storage", "wr.parsers", "wr.importing", "wr.desktop", "wr.workspace", "sqlite3", "streamlit", "pypdfium2")), (path, module)


def test_model_imports_do_not_discover_parsers_or_load_application_services():
    script = """
import importlib
import pkgutil
import sys
import wr.models
for item in pkgutil.iter_modules(wr.models.__path__):
    importlib.import_module(f"wr.models.{item.name}")
assert not any(name.startswith(("wr.parsers", "wr.storage", "wr.importing", "wr.desktop", "streamlit", "pypdfium2")) for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize("optimized", [False, True])
def test_desktop_module_entry_point_runs_synthetic_smoke_without_gui(tmp_path, optimized):
    subprocess.run(
        [sys.executable, *(["-O"] if optimized else []), "-m", "wr.desktop", "--smoke-test", str(tmp_path)],
        check=True, capture_output=True, text=True, timeout=45,
    )
    result = json.loads((tmp_path / "smoke-result.json").read_text())
    assert result["parsers"] == 8
    assert result["pdf_backend"] == "pdfium"
    assert (tmp_path / "audit.zip").is_file()


def test_selfcheck_has_no_assertions_or_test_dependencies():
    source = ROOT / "src/wr/desktop/selfcheck.py"
    tree = ast.parse(source.read_text())
    assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree))
    for path in (ROOT / "src/wr").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            else:
                continue
            assert not any(module.split(".")[0] in {"tests", "pytest"} for module in modules), path
