"""
veloctra_cli.py
===============
Command-line interface for the Veloctra Data Platform.
Allows direct execution of pipelines, schema validation, and diagnostics from CLI & CI/CD.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict
import yaml

from veloctra_core.settings import get_settings
from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_state.fsm import PipelineFSM
from veloctra_state.state_store import StateStore
from veloctra_transformers.script_engine import ScriptTransformEngine

logger = logging.getLogger("veloctra_cli")


def load_yaml_config(path: str) -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        print(f"Error: Config file '{path}' not found.", file=sys.stderr)
        sys.exit(1)
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_pipeline_command(args: argparse.Namespace) -> int:
    config = load_yaml_config(args.config)
    pipeline_name = config.get("pipeline", {}).get("name") or config.get("name", "cli_pipeline")
    tenant_id = args.tenant or config.get("tenant_id", "tenant_default")
    job_id = args.job_id or f"{pipeline_name}_{int(time.time())}"

    print(f"⚡ [Veloctra CLI] Starting pipeline '{pipeline_name}' (Job ID: {job_id}, Tenant: {tenant_id})")
    start_time = time.time()

    settings = get_settings()
    store = StateStore(adapter_type=settings.db_type, db_path=settings.sqlite_path)
    await store.connect()
    fsm = PipelineFSM()
    await fsm.create_job(job_id, tenant_id)

    orchestrator = PipelineOrchestrator(
        job_id=job_id,
        tenant_id=tenant_id,
        config=config,
        fsm=fsm,
        store=store,
    )

    try:
        total_rows = await orchestrator.run()
        elapsed = time.time() - start_time
        print(f"✅ [Veloctra CLI] Pipeline completed successfully!")
        print(f"   • Total Rows Processed: {total_rows:,}")
        print(f"   • Duration: {elapsed:.2f}s ({total_rows / max(elapsed, 0.001):,.1f} rows/sec)")
        return 0
    except Exception as exc:
        print(f"❌ [Veloctra CLI] Pipeline failed: {exc}", file=sys.stderr)
        return 1


def validate_config_command(args: argparse.Namespace) -> int:
    config = load_yaml_config(args.config)
    errors = []

    if "sources" not in config or not config["sources"]:
        errors.append("Config missing 'sources' list.")
    if "destinations" not in config or not config["destinations"]:
        errors.append("Config missing 'destinations' list.")

    # Validate custom script if present
    custom_script = config.get("custom_script", {})
    if custom_script.get("code") or custom_script.get("script_path") or custom_script.get("module_name"):
        try:
            engine = ScriptTransformEngine(
                script_code=custom_script.get("code"),
                script_path=custom_script.get("script_path"),
                module_name=custom_script.get("module_name"),
                timeout_seconds=custom_script.get("timeout_seconds", 30.0),
            )
            print("   • Custom script compiled successfully.")
        except Exception as exc:
            errors.append(f"Custom script error: {exc}")

    if errors:
        print(f"❌ [Veloctra CLI] Validation failed with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"   - {err}", file=sys.stderr)
        return 1

    pipeline_name = config.get("pipeline", {}).get("name") or "unnamed_pipeline"
    print(f"✅ [Veloctra CLI] Config '{args.config}' for pipeline '{pipeline_name}' is valid.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="veloctra",
        description="⚡ Veloctra Data Platform — Lightweight & High-Performance Data Engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Execute a pipeline from YAML configuration")
    run_parser.add_argument("-c", "--config", required=True, help="Path to pipeline YAML configuration file")
    run_parser.add_argument("-t", "--tenant", default=None, help="Tenant ID (overrides YAML setting)")
    run_parser.add_argument("-j", "--job-id", default=None, help="Custom job ID")

    # validate command
    val_parser = subparsers.add_parser("validate", help="Validate a pipeline YAML configuration")
    val_parser.add_argument("-c", "--config", required=True, help="Path to pipeline YAML configuration file")

    # version command
    subparsers.add_parser("version", help="Print Veloctra Engine version")

    args = parser.parse_args()

    if args.command == "version":
        print("Veloctra Engine v1.0.0 (High-Performance Vectorized Lightweight Data Platform)")
        sys.exit(0)
    elif args.command == "validate":
        sys.exit(validate_config_command(args))
    elif args.command == "run":
        exit_code = asyncio.run(run_pipeline_command(args))
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
