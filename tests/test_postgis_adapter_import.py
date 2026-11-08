from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


def test_postgis_adapter_imports_without_shapely_installed():
    source = f"""
import sys

sys.path.insert(0, {str(SOURCE_ROOT)!r})

class BlockShapelyImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "shapely" or fullname.startswith("shapely."):
            raise ImportError("Shapely is blocked for this import-isolation test")

sys.meta_path.insert(0, BlockShapelyImports())
import tessellatum_foundry.capabilities.postgis_vector_buffer
"""
    subprocess.run([sys.executable, "-c", source], check=True)
