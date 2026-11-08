from __future__ import annotations

import subprocess
import sys


def test_postgis_adapter_imports_without_shapely_installed():
    source = """
import sys

class BlockShapelyImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "shapely" or fullname.startswith("shapely."):
            raise ImportError("Shapely is blocked for this import-isolation test")

sys.meta_path.insert(0, BlockShapelyImports())
import tessellatum_foundry.capabilities.postgis_vector_buffer
"""
    subprocess.run([sys.executable, "-c", source], check=True)
