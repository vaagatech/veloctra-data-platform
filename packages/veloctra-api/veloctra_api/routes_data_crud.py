"""
veloctra_api/routes_data_crud.py
================================
Direct Single-Record Query API and Source/Target CRUD Operations Router.
"""

from __future__ import annotations

import time
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from veloctra_security.rbac import Role, require_role
from veloctra_security.security import TokenPayload
from veloctra_connectors.sql_connector import SQLConnector
from veloctra_connectors.nosql_connector import MongoConnector, create_nosql_connector

import re
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["Direct Single-Record & Source CRUD API"])

def snake_to_camel(name: str) -> str:
    if name == "_id":
        return "id"
    # Remove leading/trailing underscores and split
    name = name.strip("_")
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def convert_keys_to_camel(d: Any) -> Any:
    if isinstance(d, dict):
        return {snake_to_camel(k): convert_keys_to_camel(v) for k, v in d.items()}
    if isinstance(d, list):
        return [convert_keys_to_camel(i) for i in d]
    return d


class SingleRecordQueryRequest(BaseModel):
    connection_string: str
    target_type: str = "database" # database | nosql | api
    table_or_collection: str
    record_id: Optional[Any] = None
    id_field: str = "id"
    raw_query: Optional[str] = None


class CrudCreateRequest(BaseModel):
    connection_string: str
    target_type: str = "nosql" # database | nosql
    table_or_collection: str
    data: Dict[str, Any]


class CrudUpdateRequest(BaseModel):
    connection_string: str
    target_type: str = "nosql"
    table_or_collection: str
    record_id: Any
    id_field: str = "id"
    update_data: Dict[str, Any]


class CrudDeleteRequest(BaseModel):
    connection_string: str
    target_type: str = "nosql"
    table_or_collection: str
    record_id: Any
    id_field: str = "id"


@router.post("/query-record")
async def query_single_record(
    body: SingleRecordQueryRequest,
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER, Role.OPERATOR, Role.VIEWER)),
):
    """Executes direct single-record query from source or target and returns JSON API response."""
    start_ts = time.time()

    if body.target_type == "nosql" or "mongodb" in body.connection_string.lower():
        try:
            mongo_connector = MongoConnector(uri=body.connection_string, db_name="veloctra_app_db")
            await mongo_connector.connect()

            filter_query = {}
            if body.record_id is not None:
                from bson import ObjectId
                try:
                    filter_query = {"_id": ObjectId(str(body.record_id))}
                except Exception:
                    filter_query = {body.id_field: body.record_id}
            elif body.raw_query:
                try:
                    filter_query = json.loads(body.raw_query)
                except Exception:
                    filter_query = {body.id_field: body.raw_query}

            doc = await mongo_connector._db[body.table_or_collection].find_one(filter_query)
            await mongo_connector.close()

            if not doc:
                raise HTTPException(status_code=404, detail=f"Record not found in collection '{body.table_or_collection}' matching filter {filter_query}")

            if "_id" in doc:
                doc["id"] = str(doc.pop("_id"))
            
            doc_camel = convert_keys_to_camel(doc)

            elapsed_ms = round((time.time() - start_ts) * 1000, 2)
            return {
                "status": "success",
                "elapsed_ms": elapsed_ms,
                "connection": body.connection_string,
                "tableOrCollection": body.table_or_collection,
                "record": doc_camel,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"MongoDB query error: {e}")

    elif body.target_type == "api":
        import urllib.request
        try:
            url = f"{body.connection_string}/{body.table_or_collection}/{body.record_id}" if body.record_id else f"{body.connection_string}/{body.table_or_collection}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            elapsed_ms = round((time.time() - start_ts) * 1000, 2)
            return {
                "status": "success",
                "elapsed_ms": elapsed_ms,
                "connection": body.connection_string,
                "endpoint": url,
                "record": convert_keys_to_camel(data),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API GET request failed: {e}")

    else:
        # Default SQL single record lookup
        try:
            sql = body.raw_query
            if not sql:
                sql = f"SELECT * FROM {body.table_or_collection} WHERE {body.id_field} = '{body.record_id}' LIMIT 1"

            async with SQLConnector(body.connection_string) as conn:
                async for batch in conn.stream_read(sql, chunk_size=10):
                    pylist = batch.to_pylist()
                    if pylist:
                        elapsed_ms = round((time.time() - start_ts) * 1000, 2)
                        return {
                            "status": "success",
                            "elapsed_ms": elapsed_ms,
                            "connection": body.connection_string,
                            "table_or_collection": body.table_or_collection,
                            "record": pylist[0],
                        }

            raise HTTPException(status_code=404, detail=f"Record not found in table '{body.table_or_collection}' matching query {sql}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"SQL single record query error: {e}")


@router.post("/crud/create")
async def crud_create_record(
    body: CrudCreateRequest,
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER)),
):
    """Inserts a single record or document directly into the specified source or destination system."""
    if "mongodb" in body.connection_string.lower() or body.target_type == "nosql":
        mongo = MongoConnector(uri=body.connection_string, db_name="veloctra_app_db")
        await mongo.connect()
        res = await mongo._db[body.table_or_collection].insert_one(body.data)
        await mongo.close()
        return {"status": "created", "insertedId": str(res.inserted_id), "collection": body.table_or_collection}
    elif body.target_type == "api":
        import urllib.request
        try:
            url = f"{body.connection_string}/{body.table_or_collection}"
            req = urllib.request.Request(url, data=json.dumps(body.data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
            return {"status": "created", "endpoint": url, "data": res_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API POST request failed: {e}")
    else:
        # SQL insert
        cols = ", ".join(body.data.keys())
        vals = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in body.data.values())
        sql = f"INSERT INTO {body.table_or_collection} ({cols}) VALUES ({vals})"
        async with SQLConnector(body.connection_string) as conn:
            await conn.bulk_upsert(body.table_or_collection, [body.data])
        return {"status": "created", "table": body.table_or_collection, "data": body.data}


@router.get("/crud/read")
async def crud_read_record(
    connection_string: str,
    table_or_collection: str,
    record_id: str,
    id_field: str = "id",
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER, Role.OPERATOR, Role.VIEWER)),
):
    """Reads a single record by ID directly from source or destination system."""
    return await query_single_record(
        SingleRecordQueryRequest(
            connection_string=connection_string,
            table_or_collection=table_or_collection,
            record_id=record_id,
            id_field=id_field,
            target_type="nosql" if "mongodb" in connection_string.lower() else ("api" if connection_string.startswith("http") else "database"),
        ),
        token=token,
    )


@router.put("/crud/update")
async def crud_update_record(
    body: CrudUpdateRequest,
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER)),
):
    """Updates a single record or document in the source or target system."""
    if "mongodb" in body.connection_string.lower() or body.target_type == "nosql":
        mongo = MongoConnector(uri=body.connection_string, db_name="veloctra_app_db")
        await mongo.connect()
        from bson import ObjectId
        try:
            filter_query = {"_id": ObjectId(str(body.record_id))}
        except Exception:
            filter_query = {body.id_field: body.record_id}

        res = await mongo._db[body.table_or_collection].update_one(filter_query, {"$set": body.update_data})
        await mongo.close()
        return {"status": "updated", "matchedCount": res.matched_count, "modifiedCount": res.modified_count, "collection": body.table_or_collection}
    elif body.target_type == "api":
        import urllib.request
        try:
            url = f"{body.connection_string}/{body.table_or_collection}/{body.record_id}"
            req = urllib.request.Request(url, data=json.dumps(body.update_data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method="PUT")
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
            return {"status": "updated", "endpoint": url, "data": res_data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API PUT request failed: {e}")
    else:
        async with SQLConnector(body.connection_string) as conn:
            update_payload = {**body.update_data, body.id_field: body.record_id}
            await conn.bulk_upsert(body.table_or_collection, [update_payload], conflict_cols=[body.id_field])
        return {"status": "updated", "table": body.table_or_collection, "record_id": body.record_id}


@router.delete("/crud/delete")
async def crud_delete_record(
    body: CrudDeleteRequest,
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER)),
):
    """Deletes a single record or document from the source or target system."""
    if "mongodb" in body.connection_string.lower() or body.target_type == "nosql":
        mongo = MongoConnector(uri=body.connection_string, db_name="veloctra_app_db")
        await mongo.connect()
        from bson import ObjectId
        try:
            filter_query = {"_id": ObjectId(str(body.record_id))}
        except Exception:
            filter_query = {body.id_field: body.record_id}

        res = await mongo._db[body.table_or_collection].delete_one(filter_query)
        await mongo.close()
        return {"status": "deleted", "deleted_count": res.deleted_count}
    elif body.target_type == "api":
        import urllib.request
        try:
            url = f"{body.connection_string}/{body.table_or_collection}/{body.record_id}"
            req = urllib.request.Request(url, method="DELETE")
            with urllib.request.urlopen(req, timeout=10) as response:
                pass
            return {"status": "deleted", "endpoint": url, "record_id": body.record_id}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"API DELETE request failed: {e}")
    else:
        sql = f"DELETE FROM {body.table_or_collection} WHERE {body.id_field} = '{body.record_id}'"
        async with SQLConnector(body.connection_string) as conn:
            if conn._pool:
                await conn._pool.execute(sql)
        return {"status": "deleted", "table": body.table_or_collection, "record_id": body.record_id}
