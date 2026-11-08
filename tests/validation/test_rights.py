from __future__ import annotations

from tessellatum_foundry.validation.rights import build_rights_provenance_report


def artifact(*, rights=None):
    record = {"artifact_id": "source.data", "version": "1.0.0"}
    if rights is not None:
        record["rights"] = rights
    return record


def test_missing_rights_are_unknown_not_permission():
    report = build_rights_provenance_report(
        run_id="run:unknown",
        input_artifact=artifact(),
    )

    assert report["stage"] == "rights_security"
    assert report["overall_status"] == "requires_review"
    findings = {item["code"]: item for item in report["findings"]}
    assert findings["rights.declaration_missing"]["status"] == "not_assessed"
    assert findings["rights.permission_not_evaluated"]["status"] == "not_assessed"
    assert "redistribution_permission" in report["unassessed_dimensions"]


def test_recorded_license_is_not_misrepresented_as_verified_permission():
    report = build_rights_provenance_report(
        run_id="run:declared",
        input_artifact=artifact(
            rights={
                "license_id": "CC-BY-4.0",
                "attribution": "Example source",
                "source_uri": "https://example.org/data",
            }
        ),
    )

    assert report["overall_status"] == "not_assessed"
    findings = {item["code"]: item for item in report["findings"]}
    assert findings["rights.license_identifier_recorded"]["status"] == "passed"
    assert findings["rights.permission_not_evaluated"]["status"] == "not_assessed"


def test_incomplete_rights_declaration_requires_review():
    report = build_rights_provenance_report(
        run_id="run:partial",
        input_artifact=artifact(rights={"attribution": "Example source"}),
    )

    assert report["overall_status"] == "requires_review"
    findings = {item["code"]: item for item in report["findings"]}
    assert findings["rights.license_identifier_missing"]["status"] == "not_assessed"
