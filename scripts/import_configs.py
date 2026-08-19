#!/usr/bin/env python3
"""
scripts/import_configs.py
=========================
CI/CD & GitOps Pipeline Configuration Importer for Veloctra Data Platform.
Imports YAML configuration files from ./configs/ into the enterprise StateStore (MongoDB),
registers the Project Workspace entity, extracts and registers discovered database/nosql
connections using double-envelope encryption, and activates pipeline versions.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict
import yaml

from veloctra_core.settings import get_settings
from veloctra_state.config_manager import ConfigManager
from veloctra_state.state_store import StateStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ConfigImporter")


async def import_all(
    tenant_id: str = "healthcare_prod_workspace",
    project_name: str = "Healthcare Workspace",
    project_desc: str = "Enterprise Healthcare Claims & Lakehouse Processing Workspace",
    configs_dir_path: str = "configs",
):
    settings = get_settings()
    logger.info("==================================================================")
    logger.info(" ⚡ Veloctra CI/CD Config & Workspace Importer")
    logger.info("==================================================================")
    logger.info("Target Workspace ID   : %s", tenant_id)
    logger.info("Target Workspace Name : %s", project_name)
    logger.info("StateStore Backend    : %s (DB: %s)", settings.state_store_type, settings.mongo_system_db)
    logger.info("Configs Directory     : %s", configs_dir_path)
    logger.info("==================================================================")

    store = StateStore()
    await store.connect()
    config_mgr = ConfigManager()

    # Step 1: Register Project / Workspace entity in StateStore
    logger.info("1. Registering Project Workspace '%s' (%s)...", project_name, tenant_id)
    await store.save_project(
        tenant_id=tenant_id,
        proj_id=tenant_id,
        name=project_name,
        description=project_desc,
    )
    logger.info("✓ Project Workspace registered successfully in StateStore.")

    # Step 2: Read and import YAML configurations
    configs_dir = Path(configs_dir_path)
    if not configs_dir.exists():
        logger.error("Configs directory '%s' not found!", configs_dir)
        sys.exit(1)

    yaml_files = sorted(list(configs_dir.glob("*.yaml")) + list(configs_dir.glob("*.yml")))
    logger.info("2. Found %d configuration file(s) in %s", len(yaml_files), configs_dir)

    imported = 0
    for yml_file in yaml_files:
        pipeline_id = yml_file.stem
        try:
            with open(yml_file, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)

            if not isinstance(content, dict):
                logger.warning("Skipping %s: Content is not a YAML dictionary", yml_file.name)
                continue

            content["pipeline_id"] = pipeline_id
            content["project_id"] = tenant_id
            content["tenant_id"] = tenant_id

            version = await config_mgr.save(tenant_id, pipeline_id, content)
            logger.info("✓ Imported '%s' (v%d) into StateStore", pipeline_id, version)

            # Step 3: Auto-extract and register connections with Double Encryption
            def _extract_url(item: dict) -> str:
                return (
                    item.get("connection_string")
                    or item.get("url")
                    or item.get("endpoint_url")
                    or item.get("path")
                    or item.get("output_dir")
                    or item.get("redis_url")
                    or item.get("queue_url")
                    or (f"kafka://{item.get('bootstrap_servers')}" if item.get("bootstrap_servers") else None)
                    or (f"rabbitmq://{item.get('host')}:{item.get('port', 5672)}" if item.get("host") else None)
                    or (f"nats://{item.get('servers')[0]}" if item.get("servers") and isinstance(item.get("servers"), list) else None)
                    or f"{item.get('type', 'generic')}://configured"
                )

            sources = content.get("sources") or ([content["source"]] if "source" in content else [])
            for s in sources:
                stype = s.get("type", "file").lower()
                c_str = _extract_url(s)
                s_name = s.get("name") or f"{pipeline_id}_{stype}_source"
                await store.save_connection(
                    tenant_id=tenant_id,
                    conn_id=s_name.lower().replace(" ", "_").replace("-", "_"),
                    name=s_name,
                    type=stype,
                    url=c_str,
                    config_payload=s,
                )
                logger.info("  ↳ Synced Source Connection: %s (%s) -> %s", s_name, stype, c_str)

            destinations = content.get("destinations") or []
            for d in destinations:
                dtype = d.get("type", "database").lower()
                db_type = d.get("db_type", dtype).lower()
                c_str = _extract_url(d)
                d_name = d.get("name") or f"{pipeline_id}_{db_type}_dest"
                await store.save_connection(
                    tenant_id=tenant_id,
                    conn_id=d_name.lower().replace(" ", "_").replace("-", "_"),
                    name=d_name,
                    type=db_type,
                    url=c_str,
                    config_payload=d,
                )
                logger.info("  ↳ Synced Destination Connection: %s (%s) -> %s", d_name, db_type, c_str)

            imported += 1
        except Exception as exc:
            logger.error("Failed to import %s: %s", yml_file.name, exc, exc_info=True)

    # Step 4: Verify stored configurations and connections
    all_projects = await store.get_projects(tenant_id)
    all_configs = await store.get_pipeline_configs(tenant_id)
    all_conns = await store.get_connections(tenant_id)

    logger.info("==================================================================")
    logger.info("Config Import Complete: %d imported. Total active in DB: %d", imported, len(all_configs))
    logger.info("Registered Workspaces in DB: %d", len(all_projects))
    for p in all_projects:
        logger.info("  - [%s] %s: %s", p.get("id"), p.get("name"), p.get("description"))
    logger.info("Total Connections in DB (Double-Envelope Encrypted): %d", len(all_conns))
    for c in all_conns:
        logger.info("  - [%s] %s -> %s", c.get("type"), c.get("name"), c.get("url"))
    logger.info("==================================================================")

    await store.close()
    return imported


def main():
    parser = argparse.ArgumentParser(description="Veloctra CI/CD & GitOps Config Importer")
    parser.add_argument("-w", "--workspace", default="healthcare_prod_workspace", help="Workspace / Tenant ID")
    parser.add_argument("-n", "--name", default="Healthcare Workspace", help="Workspace Name")
    parser.add_argument("-d", "--desc", default="Enterprise Healthcare Claims & Lakehouse Processing Workspace", help="Workspace Description")
    parser.add_argument("-c", "--dir", default="configs", help="Configs directory path")
    args = parser.parse_args()

    asyncio.run(import_all(
        tenant_id=args.workspace,
        project_name=args.name,
        project_desc=args.desc,
        configs_dir_path=args.dir,
    ))


if __name__ == "__main__":
    main()
