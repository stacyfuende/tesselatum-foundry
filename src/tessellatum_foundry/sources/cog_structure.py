"""Conservative TIFF/COG structural checks (not a formal conformance validator)."""
from __future__ import annotations

from dataclasses import dataclass

from .tiff import TiffDirectory


@dataclass(frozen=True, slots=True)
class TiffStructureAssessment:
    """Observed structure and reasons a file is not a COG-like candidate."""

    candidate: bool
    checks: tuple[str, ...]
    issues: tuple[str, ...]


def assess_cog_structure(directories: tuple[TiffDirectory, ...]) -> TiffStructureAssessment:
    """Assess limited structural properties without claiming COG conformance.

    This checks tiled directories, expected tile-grid table counts, directory
    dimensions/roles, and consistent tile geometry. It does not verify byte
    ordering, GeoKeys/CRS, compression semantics, offsets/alignment, or pixel
    decoding and therefore is not an OGC conformance verdict.
    """
    checks: list[str] = []
    issues: list[str] = []
    if not directories:
        return TiffStructureAssessment(False, (), ("No TIFF directories were supplied.",))

    first = directories[0]
    if not first.tiled:
        issues.append("Primary directory is strip-based; COG-style tiling is absent.")
    else:
        checks.append("Primary directory is tiled.")

    if first.tile_width is None or first.tile_height is None:
        issues.append("Primary directory has no tile dimensions.")
    else:
        tile_shape = (first.tile_width, first.tile_height)
        checks.append("Primary tile dimensions are available.")

    for index, directory in enumerate(directories[1:], start=1):
        if directory.width >= first.width or directory.height >= first.height:
            issues.append(f"Directory {index} is not smaller than the primary image.")
        else:
            checks.append(f"Directory {index} dimensions decrease.")

        if not (directory.new_subfile_type & 1):
            issues.append(f"Directory {index} is not marked as a reduced-resolution image.")
        else:
            checks.append(f"Directory {index} is marked reduced-resolution.")

        if not directory.tiled:
            issues.append(f"Directory {index} is strip-based.")
        elif (directory.tile_width, directory.tile_height) != (
            first.tile_width, first.tile_height
        ):
            issues.append(f"Directory {index} tile dimensions differ from the primary image.")
        else:
            checks.append(f"Directory {index} uses matching tile dimensions.")

        if directory.samples_per_pixel != first.samples_per_pixel:
            issues.append(f"Directory {index} samples-per-pixel differs from the primary image.")
        if directory.planar_configuration != first.planar_configuration:
            issues.append(f"Directory {index} planar configuration differs from the primary image.")

    return TiffStructureAssessment(not issues, tuple(checks), tuple(issues))
