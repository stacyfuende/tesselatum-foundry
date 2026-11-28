from __future__ import annotations

import hashlib

import pytest

from tessellatum_foundry.api.tenant_runtime import LocalTenantRuntimeResolver


def test_local_tenant_runtime_is_stable_and_isolated(tmp_path):
    resolve = LocalTenantRuntimeResolver(tmp_path)

    first = resolve("tenant-alpha")
    first_again = resolve("tenant-alpha")
    second = resolve("tenant-beta")

    assert first is first_again
    assert first["artifact_store"] is first_again["artifact_store"]
    assert first["artifact_store"] is not second["artifact_store"]
    assert first["capabilities"] is not second["capabilities"]
    assert first["recipe_service"] is not second["recipe_service"]

    alpha_root = tmp_path / hashlib.sha256(b"tenant-alpha").hexdigest()
    beta_root = tmp_path / hashlib.sha256(b"tenant-beta").hexdigest()
    assert alpha_root.is_dir()
    assert beta_root.is_dir()
    assert alpha_root != beta_root

    assert first["cell_templates"]["standardize"]["capability"] == {
        "capability_id": "vector.reproject",
        "version": "1.0.0",
    }
    assert first["output_bindings"] == {
        "standardized-sites": {
            "node_id": "standardize",
            "output_port": "result",
        },
    }


@pytest.mark.parametrize("tenant_id", ["", "  ", None])
def test_local_tenant_runtime_requires_trusted_nonempty_tenant_id(
    tmp_path, tenant_id
):
    resolve = LocalTenantRuntimeResolver(tmp_path)
    with pytest.raises(ValueError, match="trusted non-empty tenant ID"):
        resolve(tenant_id)


@pytest.mark.parametrize("tenant_id", ["../outside", "/tmp/escape"])
def test_tenant_identifier_cannot_escape_runtime_root(tmp_path, tenant_id):
    resolve = LocalTenantRuntimeResolver(tmp_path)
    resolve(tenant_id)

    expected = tmp_path / hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()
    assert expected.is_dir()
    assert expected.parent == tmp_path
    assert not (tmp_path.parent / "outside").exists()
    assert not (tmp_path / "escape").exists()
