"""`scripts/new_schema_version.py` and the documented move of the latest pointer, tried on a scratch copy of the
package: the next version, scaffolded and made the latest, passes its own tests and the version-neutral ones."""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "new_schema_version", ROOT / "scripts" / "new_schema_version.py"
)
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def scratch_copy(tmp_path: Path) -> Path:
    for directory in ("icoschema", "test"):
        shutil.copytree(
            ROOT / directory,
            tmp_path / directory,
            ignore=shutil.ignore_patterns("__pycache__", "v[2-9]*"),
        )
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    return tmp_path


def test_the_scaffold_copies_the_version_and_registers_it(tmp_path: Path) -> None:
    root = scratch_copy(tmp_path)
    assert script.scaffold(root) == (1, 2)
    assert (root / "icoschema" / "v2" / "schema" / "dataset.yaml").exists()
    assert (root / "test" / "v2" / "data").is_dir()
    assert '    2: "icoschema.v2",' in (root / "icoschema" / "_schemas.py").read_text()
    assert "icoschema.v1" not in "".join(
        p.read_text(encoding="utf-8")
        for p in (root / "icoschema" / "v2").rglob("*.py")
        if "generated" not in p.parts
    )


def test_a_scaffolded_version_made_the_latest_passes_its_tests(tmp_path: Path) -> None:
    root = scratch_copy(tmp_path)
    script.scaffold(root)
    # the documented move of the latest pointer
    schemas = root / "icoschema" / "_schemas.py"
    schemas.write_text(
        re.sub(r"LATEST: int = 1", "LATEST: int = 2", schemas.read_text())
    )
    init = root / "icoschema" / "__init__.py"
    text = init.read_text().replace(
        "from icoschema import v1\n", "from icoschema import v1, v2\n"
    )
    init.write_text(
        text.replace("from icoschema.v1 import (", "from icoschema.v2 import (")
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "test/test_schemas.py",
            "test/v2",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]
