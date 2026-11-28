"""Independent structural checks for bounded raster-window execution output."""

from __future__ import annotations

from dataclasses import dataclass

from tessellatum_foundry.sources.raster import RasterContractError, RasterMetadata, RasterWindow
from tessellatum_foundry.sources.window_assembly import RasterWindowBuffer


@dataclass(frozen=True, slots=True)
class RasterOutputFinding:
    code: str
    status: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class RasterWindowInspection:
    findings: tuple[RasterOutputFinding, ...]
    sample_count: int
    byte_count: int

    @property
    def passed(self) -> bool:
        return bool(self.findings) and all(
            finding.status == "passed" for finding in self.findings
        )


_DTYPE_BYTES = {
    "uint8": 1, "int8": 1, "uint16": 2, "int16": 2,
    "uint32": 4, "int32": 4, "uint64": 8, "int64": 8,
    "float32": 4, "float64": 8,
}


def inspect_raster_window_output(
    *,
    buffer: RasterWindowBuffer,
    metadata: RasterMetadata,
    requested_window: RasterWindow,
    requested_bands: tuple[int, ...] = (),
    validity: tuple[bool, ...] | None = None,
    max_output_bytes: int = 256 * 1024 * 1024,
) -> RasterWindowInspection:
    """Validate exact raster-window shape, band order, byte count and validity.

    This critic does not certify source authenticity, COG conformance, pixel
    semantics, or CRS transformations. Those require separate evidence.
    """
    findings: list[RasterOutputFinding] = []

    def add(code: str, passed: bool, message: str) -> None:
        findings.append(RasterOutputFinding(
            code=code,
            status="passed" if passed else "failed",
            severity="info" if passed else "error",
            message=message,
        ))

    expected_bands = requested_bands or tuple(range(1, metadata.band_count + 1))
    add(
        "raster.window_matches_request",
        buffer.window == requested_window,
        "Output pixel window exactly matches the normalized request."
        if buffer.window == requested_window
        else "Output pixel window differs from the normalized request.",
    )
    add(
        "raster.band_order_matches_request",
        buffer.bands == expected_bands
        and len(buffer.dtypes) == len(expected_bands),
        "Output bands preserve the requested one-based band order."
        if buffer.bands == expected_bands and len(buffer.dtypes) == len(expected_bands)
        else "Output band selection or order differs from the request.",
    )
    try:
        requested_window.validate_against(metadata)
        expected_dtypes = tuple(metadata.dtypes[band - 1] for band in expected_bands)
        widths = tuple(_DTYPE_BYTES[dtype] for dtype in expected_dtypes)
        expected_bytes = requested_window.width * requested_window.height * sum(widths)
        supported = True
    except (RasterContractError, IndexError, KeyError, TypeError):
        expected_bytes = -1
        supported = False
    add(
        "raster.source_grid_and_dtypes",
        supported and buffer.dtypes == expected_dtypes,
        "Requested window and sample dtypes are valid on the selected source grid."
        if supported and buffer.dtypes == expected_dtypes
        else "Requested window or sample dtypes are invalid for the selected source grid.",
    )
    add(
        "raster.output_byte_length",
        supported and len(buffer.samples) == expected_bytes
        and expected_bytes <= max_output_bytes,
        "Output byte length exactly matches the declared pixel grid and budget."
        if supported and len(buffer.samples) == expected_bytes
        and expected_bytes <= max_output_bytes
        else "Output byte length differs from its declared grid or exceeds the budget.",
    )
    pixel_count = requested_window.width * requested_window.height
    add(
        "raster.validity_mask",
        validity is None or len(validity) == pixel_count,
        "Validity mask has one entry per output pixel."
        if validity is None or len(validity) == pixel_count
        else "Validity mask length does not match the output pixel count.",
    )
    add(
        "raster.byte_order",
        buffer.byte_order in {"little", "big"},
        "Output sample byte order is explicitly declared."
        if buffer.byte_order in {"little", "big"}
        else "Output sample byte order is unsupported.",
    )
    return RasterWindowInspection(
        findings=tuple(findings),
        sample_count=pixel_count * len(buffer.bands),
        byte_count=len(buffer.samples),
    )
