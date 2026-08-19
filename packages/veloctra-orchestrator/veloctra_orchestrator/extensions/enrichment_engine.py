import pyarrow as pa
import logging
import json
import urllib.request
from typing import List, Dict, Any
from veloctra_connectors.sql_connector import SQLConnector
from veloctra_connectors.nosql_connector import create_nosql_connector

logger = logging.getLogger(__name__)

class EnrichmentEngine:
    def __init__(self, enrichments: List[Dict[str, Any]]):
        self.enrichments = enrichments

    async def apply_enrichments(self, batch: pa.RecordBatch) -> pa.RecordBatch:
        if not self.enrichments or batch.num_rows == 0:
            return batch

        # Convert to dictionary for easy manipulation
        records = batch.to_pylist()

        for enrichment in self.enrichments:
            src = enrichment.get("source", {})
            stype = src.get("type", "api")
            join_key = enrichment.get("join_key")
            target_field = enrichment.get("target_field")

            if not join_key or not target_field:
                continue

            # Fetch secondary data and build lookup map
            lookup_map = await self._fetch_secondary_data(src, records, join_key)
            
            # Apply to records
            for record in records:
                key_val = record.get(join_key)
                if key_val is not None:
                    # By default we merge fields to the root, unless target_field specifies a nest
                    enrichment_data = lookup_map.get(key_val, {})
                    if target_field == "_flatten_":
                        record.update(enrichment_data)
                    else:
                        record[target_field] = enrichment_data

        return pa.RecordBatch.from_pylist(records)

    async def _fetch_secondary_data(self, src: Dict[str, Any], records: List[Dict[str, Any]], join_key: str) -> Dict[Any, Any]:
        """Fetches data from the secondary source and maps it by join_key"""
        stype = src.get("type", "api")
        lookup_map = {}
        
        # Get unique keys to lookup
        keys = list(set(r.get(join_key) for r in records if r.get(join_key) is not None))
        if not keys:
            return {}

        if stype == "api":
            try:
                # Bulk API lookup (if API supports batch) or we do single queries (inefficient for large batches)
                # Assuming the API endpoint supports ?keys=...
                url = src.get("endpoint_url", "")
                if url:
                    # In a real enterprise system we'd use aiohttp for async, using urllib for simplicity here
                    import urllib.parse
                    keys_str = ",".join(map(str, keys))
                    req_url = f"{url}?keys={urllib.parse.quote(keys_str)}"
                    req = urllib.request.Request(req_url, method="GET")
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode("utf-8"))
                        if isinstance(data, list):
                            for item in data:
                                if join_key in item:
                                    lookup_map[item[join_key]] = item
            except Exception as e:
                logger.error(f"[EnrichmentEngine] API fetch error: {e}")

        elif stype == "database":
            try:
                keys_str = ",".join(f"'{k}'" if isinstance(k, str) else str(k) for k in keys)
                query = f"SELECT * FROM {src['table']} WHERE {join_key} IN ({keys_str})"
                async with SQLConnector(src["connection_string"]) as conn:
                    async for batch in conn.stream_read(query, chunk_size=10000):
                        for item in batch.to_pylist():
                            lookup_map[item[join_key]] = item
            except Exception as e:
                logger.error(f"[EnrichmentEngine] Database fetch error: {e}")

        elif stype == "nosql":
            try:
                adapter = create_nosql_connector(src)
                async with adapter:
                    query = {join_key: {"$in": keys}}
                    async for batch in adapter.stream_read(src.get("collection"), query, chunk_size=10000):
                        for item in batch.to_pylist():
                            lookup_map[item[join_key]] = item
            except Exception as e:
                logger.error(f"[EnrichmentEngine] NoSQL fetch error: {e}")

        return lookup_map
