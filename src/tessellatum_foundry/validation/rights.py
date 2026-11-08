"""Rights declaration and lineage evidence for spatial Artifacts."""

from __future__ import annotations

from typing import Any

from tessellatum_foundry.storage.artifacts import utc_timestamp


def build_rights_provenance_report(
    *,
    run_id: str,
    input_artifact: dict[str, Any],
    output_artifact: dict[str, Any],
) -> dict[str, Any]:
    """Record rights metadata presence without interpreting legal permissions.

    Missing or incomplete rights metadata is never treated as permission.
    A declared licence identifier is preserved as a declaration, not verified
    as authentic, applicable, or sufficient for a proposed downstream use.
    """
    reference = (
        f"{input_artifact['artifact_id']}@{input_artifact['version']}"
    )
    rights = input_artifact.get("rights")
    findings: list[dict[str, Any]] = []
    if rights is None:
        declaration_status = "unknown"
        overall_status = "requires_review"
        findings.append({
            "code": "rights.declaration_missing",
            "severity": "warning",
            "status": "not_assessed",
            "message": "The input Artifact has no rights declaration.",
            "json_pointer": "/rights",
            "evidence": [{
                "kind": "artifact",
                "reference": reference,
                "summary": "Input Artifact metadata contains no rights object.",
            }],
            "recommendation": (
                "Record the source rights and licence evidence before relying "
                "on permission to use, publish, or redistribute this data."
            ),
        })
    else:
        declaration_status = "declared_unverified"
        license_id = rights.get("license_id")
        if isinstance(license_id, str) and license_id.strip():
            findings.append({
                "code": "rights.license_identifier_recorded",
                "severity": "info",
                "status": "passed",
                "message": "A licence identifier is recorded in Artifact metadata.",
                "json_pointer": "/rights/license_id",
                "evidence": [{
                    "kind": "artifact",
                    "reference": reference,
                    "summary": (
                        "Licence identifier is present; its terms were not interpreted."
                    ),
                }],
            })
            overall_status = "not_assessed"
        else:
            findings.append({
                "code": "rights.license_identifier_missing",
                "severity": "warning",
                "status": "not_assessed",
                "message": (
                    "Rights metadata exists but does not identify a licence."
                ),
                "json_pointer": "/rights/license_id",
                "evidence": [{
                    "kind": "artifact",
                    "reference": reference,
                    "summary": "Rights object is present without a licence identifier.",
                }],
                "recommendation": (
                    "Supply an authoritative licence identifier or document "
                    "the applicable rights basis for review."
                ),
            })
            overall_status = "requires_review"

    output_metadata = output_artifact.get("metadata", {})
    rights_provenance = (
        output_metadata.get("rights_provenance")
        if isinstance(output_metadata, dict)
        else None
    )
    expected_source = {
        "artifact_id": input_artifact["artifact_id"],
        "version": input_artifact["version"],
    }
    expected_declaration_status = (
        "declared_unverified" if rights is not None else "unknown"
    )
    inherited = (
        output_artifact.get("rights") == rights
        and isinstance(output_metadata, dict)
        and isinstance(rights_provenance, dict)
        and rights_provenance.get("source_artifact") == expected_source
        and rights_provenance.get("declaration_status") == expected_declaration_status
    )
    if inherited:
        findings.append({
            "code": "rights.declaration_inherited",
            "severity": "info",
            "status": "passed",
            "message": "The output preserves the input rights declaration and source reference.",
            "json_pointer": "/rights",
            "evidence": [{
                "kind": "artifact",
                "reference": (
                    f"{output_artifact['artifact_id']}@{output_artifact['version']}"
                ),
                "summary": "Output rights metadata and immediate source reference match the input.",
            }],
        })
    else:
        overall_status = "failed"
        findings.append({
            "code": "rights.declaration_inheritance_failed",
            "severity": "error",
            "status": "failed",
            "message": "Output rights metadata or its source Artifact reference does not match the input.",
            "json_pointer": "/rights",
            "evidence": [{
                "kind": "artifact",
                "reference": (
                    f"{output_artifact.get('artifact_id', 'unknown')}"
                    f"@{output_artifact.get('version', 'unknown')}"
                ),
                "summary": "Output metadata failed the rights inheritance check.",
            }],
            "recommendation": "Preserve the exact input rights declaration and source Artifact reference.",
        })

    findings.append({
        "code": "rights.permission_not_evaluated",
        "severity": "warning",
        "status": "not_assessed",
        "message": (
            "Foundry has not determined whether the licence permits this "
            "operation, its intended purpose, publication, or redistribution."
        ),
        "json_pointer": "/rights",
        "evidence": [{
            "kind": "artifact",
            "reference": reference,
            "summary": (
                "The exact input Artifact is recorded; no legal interpretation "
                "or intended-use authorization was performed."
            ),
        }],
        "recommendation": (
            "Evaluate the authoritative licence terms against the intended "
            "operation, audience, jurisdiction, and distribution model."
        ),
    })

    return {
        "report_id": f"report:{run_id}:rights",
        "subject": {"kind": "run", "id": run_id},
        "stage": "rights_security",
        "overall_status": overall_status,
        "created_at": utc_timestamp(),
        "validator": {
            "name": "foundry-rights-provenance-critic",
            "version": "0.1.0",
        },
        "findings": findings,
        "summary": (
            "Rights metadata presence and input lineage were recorded. "
            "This report does not grant or determine legal permission."
        ),
        "assessed_dimensions": [
            "input_artifact_identity",
            "rights_metadata_presence",
            "rights_metadata_inheritance",
        ],
        "unassessed_dimensions": [
            "license_terms_interpretation",
            "intended_use_authorization",
            "publication_permission",
            "redistribution_permission",
            "jurisdictional_legal_review",
        ],
    }
