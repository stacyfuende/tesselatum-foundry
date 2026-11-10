"""Smoke-test canonical schemas and manifests from an installed distribution."""

from tessellatum_foundry.execution.capabilities import CapabilityRegistry
from tessellatum_foundry.execution.implementations import ImplementationRegistry
from tessellatum_foundry.validation.contracts import ContractRegistry


def main() -> None:
    contracts = ContractRegistry()
    implementations = ImplementationRegistry(contracts=contracts)
    capabilities = CapabilityRegistry(contracts=contracts)
    if len(contracts.schemas) != 9:
        raise SystemExit(f"Expected 9 installed schemas, found {len(contracts.schemas)}.")
    capabilities.get("vector.buffer", "1.0.0")
    capabilities.get("raster.band_statistics", "1.0.0")
    raster_manifest = implementations.get("raster-band-statistics-rasterio", "1.0.0")
    if raster_manifest["conformance"]["status"] != "not_run":
        raise SystemExit("Raster implementation must remain gated until conformance passes.")
    implementations.require_conformant(
        implementation_id="vector-buffer-shapely",
        version="1.0.0",
        capability_id="vector.buffer",
        capability_version="1.0.0",
    )
    implementations.require_conformant(
        implementation_id="vector-buffer-postgis",
        version="1.0.0",
        capability_id="vector.buffer",
        capability_version="1.0.0",
    )
    print(
        "Installed Foundry schemas, Capability contracts, and implementation "
        "manifests resolved successfully."
    )


if __name__ == "__main__":
    main()
