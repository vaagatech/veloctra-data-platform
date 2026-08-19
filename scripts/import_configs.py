#!/usr/bin/env python3
"""
scripts/import_configs.py
=========================
CI/CD Pipeline Configuration Importer.
Imports YAML configuration files from ./configs/ into the enterprise StateStore (MongoDB),
extracts and registers discovered database/nosql connections using double-envelope encryption,
and activates pipeline versions without manual intervention.
"""

import asyncio
import logging
import sys
from pathlib import Path
import yaml

from veloctra_core.settings import get_settings
from veloctra_state.config_manager import ConfigManager
from veloctra_state.state_store import StateStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ConfigImporter")


async def import_all(tenant_id: str = "finance_prod_workspace"):
    settings = get_settings()
    logger.info("Initializing StateStore (Type: %s, Database: %s)...", settings.state_store_type, settings.mongo_system_db)
    
    store = StateStore()
    await store.connect()
    config_mgr = ConfigManager()

    configs_dir = Path("configs")
    if not configs_dir.exists():
        logger.error("Configs directory '%s' not found!", configs_dir)
        sys.exit(1)

    yaml_files = sorted(list(configs_dir.glob("*.yaml")) + list(configs_dir.glob("*.yml")))
    logger.info("Found %d configuration file(s) in %s", len(yaml_files), configs_dir)

    imported = 0
    for yml_file in yaml_files:
        pipeline_id = yml_file.stem
        try:
            with open(yml_file, "r") as f:
                content = yaml.safe_load(f)

            if not isinstance(content, dict):
                logger.warning("Skipping %s: Content is not a YAML dictionary", yml_file.name)
                continue

            content["pipeline_id"] = pipeline_id
            content["project_id"] = tenant_id

            version = await config_mgr.save(tenant_id, pipeline_id, content)
            logger.info("✓ Imported '%s' (v%d) into MongoDB", pipeline_id, version)

            # Auto-extract and register connections into MongoDB with Double Encryption
            sources = content.get("sources") or ([content["source"]] if "source" in content else [])
            for s in sources:
                stype = s.get("type", "").lower()
                c_str = s.get("connection_string") or s.get("url") or s.get("endpoint_url")
                s_name = s.get("name") or f"{pipeline_id}_{stype}_source"
                if c_str:
                    await store.save_connection(
                        tenant_id=tenant_id,
                        conn_id=s_name.lower().replace(" ", "_").replace("-", "_"),
                        name=s_name,
                        type=stype,
                        url=c_str,
                        config_payload=s,
                    )
                    logger.info("  ↳ Synced Source Connection: %s (%s)", s_name, stype)

            destinations = content.get("destinations") or []
            for d in destinations:
                dtype = d.get("type", "").lower()
                db_type = d.get("db_type", dtype).lower()
                c_str = d.get("connection_string") or d.get("url") or d.get("output_dir")
                d_name = d.get("name") or f"{pipeline_id}_{db_type}_dest"
                if c_str:
                    await store.save_connection(
                        tenant_id=tenant_id,
                        conn_id=d_name.lower().replace(" ", "_").replace("-", "_"),
                        name=d_name,
                        type=db_type,
                        url=c_str,
                        config_payload=d,
                    )
                    logger.info("  ↳ Synced Destination Connection: %s (%s)", d_name, db_type)

            imported += 1
        except Exception as exc:
            logger.error("Failed to import %s: %s", yml_file.name, exc, exc_info=True)

    # Verify stored configurations and connections
    all_configs = await store.get_pipeline_configs(tenant_id)
    all_conns = await store.get_connections(tenant_id)
    logger.info("==================================================================")
    logger.info("Config Import Complete: %d imported. Total active in DB: %d", imported, len(all_configs))
    logger.info("Total Connections in DB: %d", len(all_conns))
    for c in all_conns:
        logger.info("  - [%s] %s -> %s", c.get("type"), c.get("name"), c.get("url"))
    logger.info("==================================================================")

    await store.close()


if __name__ == "__main__":
    asyncio.run(import_all())
