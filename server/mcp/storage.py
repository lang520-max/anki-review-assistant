"""Transactional, owner-scoped snapshots with revision leases and deletion tombstones."""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
from .models import Snapshot, SyncBatch


class Conflict(Exception):
    pass


class Store:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.postgres = dsn.startswith(("postgresql://", "postgres://"))
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS collections (
                owner TEXT NOT NULL, id TEXT NOT NULL, revision BIGINT NOT NULL,
                payload TEXT NOT NULL, batch TEXT NOT NULL, deleted INTEGER NOT NULL,
                updated BIGINT NOT NULL, PRIMARY KEY(owner,id))""")

    @contextmanager
    def connection(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(self.dsn, row_factory=dict_row)
        else:
            conn = sqlite3.connect(self.dsn, timeout=30)
            conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, db, sql, params=()):
        return db.execute(sql.replace("?", "%s") if self.postgres else sql, params)

    def lock(self, db, owner, collection_id):
        if self.postgres:
            key = int.from_bytes(hashlib.sha256(f"{owner}\0{collection_id}".encode()).digest()[:8], "big", signed=True)
            db.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        else:
            db.execute("BEGIN IMMEDIATE")

    def sync(self, owner: str, collection_id: str, batch: SyncBatch):
        with self.connection() as db:
            self.lock(db, owner, collection_id)
            row = self.execute(db, "SELECT * FROM collections WHERE owner=? AND id=?", (owner,collection_id)).fetchone()
            revision = row["revision"] if row else 0
            # A retried already-applied batch succeeds without recreating deleted data.
            if row and not row["deleted"] and row["batch"] == batch.batchId:
                return {"revision": revision, "duplicate": True}
            if batch.baseRevision != revision:
                raise Conflict(f"Revision mismatch; current revision is {revision}")
            previous = json.loads(row["payload"]) if row and not row["deleted"] else {}
            if batch.snapshot is not None:
                snapshot = batch.snapshot
            else:
                data = dict(batch.metadata or {})
                if set(data) & {"decks", "notes", "cards", "reviews"}:
                    raise ValueError("Entity rows must be in upserts")
                for table in ("decks", "notes", "cards", "reviews"):
                    entities = {v["id"]: v for v in previous.get(table, [])}
                    changed = batch.upserts.get(table, [])
                    if len({v.get("id") for v in changed}) != len(changed):
                        raise ValueError("Duplicate upsert IDs")
                    for key in batch.deletes.get(table, []):
                        entities.pop(key, None)
                    for value in changed:
                        if value.get("id") in batch.deletes.get(table, []):
                            raise ValueError("Cannot delete and upsert the same ID")
                        entities[value.get("id")] = value
                    data[table] = list(entities.values())
                snapshot = Snapshot.model_validate(data)
            if snapshot.collectionId != collection_id:
                raise ValueError("Collection ID mismatch")
            changes = {}
            for table in ("decks", "notes", "cards", "reviews"):
                before = {v["id"]: v for v in previous.get(table, [])}
                after = {v.id: v.model_dump() for v in getattr(snapshot, table)}
                changes[table] = {"upserted": sum(before.get(k) != v for k,v in after.items()),
                                  "deleted": len(before.keys() - after.keys())}
            self.execute(db, """INSERT INTO collections VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(owner,id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,
                batch=excluded.batch,deleted=0,updated=excluded.updated""",
                (owner,collection_id,revision+1,snapshot.model_dump_json(),batch.batchId,0,int(time.time()*1000)))
            return {"revision": revision+1, "duplicate": False, "changes": changes}

    def get(self, owner: str, collection_id: str) -> Snapshot:
        with self.connection() as db:
            row = self.execute(db, "SELECT payload FROM collections WHERE owner=? AND id=? AND deleted=0", (owner,collection_id)).fetchone()
            if not row:
                raise KeyError("Collection not found")
            return Snapshot.model_validate_json(row["payload"])

    def status(self, owner: str):
        with self.connection() as db:
            return [dict(row) for row in self.execute(db,
                "SELECT id,revision,updated,deleted FROM collections WHERE owner=? ORDER BY id", (owner,)).fetchall()]

    def delete(self, owner: str, collection_id: str):
        with self.connection() as db:
            self.lock(db,owner,collection_id)
            row = self.execute(db,"SELECT revision FROM collections WHERE owner=? AND id=?",(owner,collection_id)).fetchone()
            revision = (row["revision"] if row else 0) + 1
            self.execute(db,"""INSERT INTO collections VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(owner,id) DO UPDATE SET revision=excluded.revision,payload='{}',batch='',deleted=1,updated=excluded.updated""",
                (owner,collection_id,revision,"{}","",1,int(time.time()*1000)))
            return {"deleted": True, "revision": revision}
