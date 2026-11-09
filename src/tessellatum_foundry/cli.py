"""Operator CLI for local Tessellatum Foundry workspaces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from tessellatum_foundry import __version__
from tessellatum_foundry.local import LocalFoundry


def _json_file(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))


def _workspace(args: argparse.Namespace) -> LocalFoundry:
    return LocalFoundry(Path(args.data_dir))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="foundry",
        description="Create, inspect, and execute local Tessellatum Foundry workspaces.",
    )
    parser.add_argument(
        "--data-dir",
        default="./foundry-data",
        help="Persistent workspace directory (default: ./foundry-data).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="Initialize or open a local workspace.")

    artifact = commands.add_parser("artifact", help="Store, inspect, and export Artifacts.")
    artifact_commands = artifact.add_subparsers(dest="artifact_command", required=True)
    put = artifact_commands.add_parser("put", help="Register immutable Artifact bytes.")
    put.add_argument("--id", required=True, dest="artifact_id")
    put.add_argument("--version", required=True)
    put.add_argument("--file", required=True, type=Path)
    put.add_argument("--created-by", required=True)
    put.add_argument("--media-type", required=True)
    put.add_argument("--format", required=True, dest="format_name")
    put.add_argument("--spatial-json", type=Path)
    put.add_argument("--rights-json", type=Path)
    put.add_argument("--metadata-json", type=Path)

    show_artifact = artifact_commands.add_parser("show", help="Show Artifact metadata.")
    show_artifact.add_argument("--id", required=True, dest="artifact_id")
    show_artifact.add_argument("--version", required=True)

    export = artifact_commands.add_parser("export", help="Export checksum-verified bytes.")
    export.add_argument("--id", required=True, dest="artifact_id")
    export.add_argument("--version", required=True)
    export.add_argument("--output", required=True, type=Path)

    register_cell = commands.add_parser("cell", help="Register an immutable Cell definition.")
    register_cell.add_argument("register", choices=["register"])
    register_cell.add_argument("--file", required=True, type=Path)
    register_cell.add_argument("--created-by", required=True)

    recipe = commands.add_parser("recipe", help="Validate and execute registered Recipes.")
    recipe_commands = recipe.add_subparsers(dest="recipe_command", required=True)
    recipe_commands.add_parser("register", help="Register a Recipe JSON document.").add_argument(
        "--file", required=True, type=Path
    )
    recipe_register = recipe_commands.choices["register"]
    recipe_register.add_argument("--created-by", required=True)
    execute = recipe_commands.add_parser("run", help="Execute an exact registered Recipe.")
    execute.add_argument("--id", required=True, dest="recipe_id")
    execute.add_argument("--version", required=True)
    execute.add_argument("--actor-id", required=True)

    run = commands.add_parser("run", help="Inspect a persisted Run.")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    show_run = run_commands.add_parser("show", help="Show a Run record.")
    show_run.add_argument("run_id")

    runs = commands.add_parser("runs", help="List persisted Runs.")
    runs.add_argument("--recipe-execution-id")

    report = commands.add_parser("report", help="Inspect validation evidence.")
    report_commands = report.add_subparsers(dest="report_command", required=True)
    show_report = report_commands.add_parser("show", help="Show a Validation Report.")
    show_report.add_argument("report_id")

    commands.add_parser("capabilities", help="List canonical Capability contracts.")
    commands.add_parser("implementations", help="List registered implementations.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            foundry = _workspace(args)
            _emit(
                {
                    "status": "ready",
                    "workspace": str(foundry.root),
                    "capabilities": len(foundry.capabilities.list()),
                    "implementations": len(foundry.implementations.list()),
                }
            )
            return 0

        foundry = _workspace(args)
        if args.command == "artifact":
            if args.artifact_command == "put":
                record = foundry.store_artifact(
                    artifact_id=args.artifact_id,
                    version=args.version,
                    content=args.file.read_bytes(),
                    created_by=args.created_by,
                    media_type=args.media_type,
                    format_name=args.format_name,
                    spatial=_json_file(args.spatial_json),
                    rights=_json_file(args.rights_json),
                    metadata=_json_file(args.metadata_json),
                )
                _emit(record)
            elif args.artifact_command == "show":
                _emit(foundry.get_artifact(args.artifact_id, args.version))
            else:
                record = foundry.get_artifact(args.artifact_id, args.version)
                content = foundry.read_artifact(record)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(content)
                _emit(
                    {
                        "status": "exported",
                        "artifact_id": args.artifact_id,
                        "version": args.version,
                        "bytes": len(content),
                        "output": str(args.output.resolve()),
                        "checksum_verified": True,
                    }
                )
            return 0

        if args.command == "cell":
            definition = _json_file(args.file)
            _emit(foundry.register_cell(definition, created_by=args.created_by))
            return 0

        if args.command == "recipe":
            if args.recipe_command == "register":
                definition = _json_file(args.file)
                _emit(foundry.register_recipe(definition, created_by=args.created_by))
                return 0
            result = foundry.execute_recipe(
                recipe_id=args.recipe_id,
                version=args.version,
                actor_id=args.actor_id,
            )
            _emit(
                {
                    "execution_id": result.execution_id,
                    "recipe": result.recipe,
                    "status": result.status,
                    "failed_node_id": result.failed_node_id,
                    "error": result.error,
                    "runs": [
                        {
                            "node_id": node_id,
                            "run_id": item.run.get("run_id"),
                            "status": item.run.get("status"),
                            "error": item.run.get("error"),
                        }
                        for node_id, item in result.node_results.items()
                    ],
                    "outputs": result.outputs,
                }
            )
            return 0 if result.status == "succeeded" else 1

        if args.command == "run":
            _emit(foundry.get_run(args.run_id))
            return 0

        if args.command == "runs":
            records = foundry.runs.list_runs()
            if args.recipe_execution_id:
                records = [
                    item
                    for item in records
                    if item.get("recipe_execution_id") == args.recipe_execution_id
                ]
            _emit(records)
            return 0

        if args.command == "report":
            _emit(foundry.get_validation_report(args.report_id))
            return 0

        if args.command == "capabilities":
            _emit(foundry.capabilities.list())
            return 0

        if args.command == "implementations":
            _emit(foundry.implementations.list())
            return 0

        parser.error("Unsupported command.")
    except (OSError, ValueError, KeyError, RuntimeError, TypeError) as error:
        print(f"foundry: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
