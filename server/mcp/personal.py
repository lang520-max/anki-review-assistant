"""Small personal service: paired phone uploads, atomic snapshots, SSH-only analysis.

No AnkiWeb credentials or write-back to the phone. Run behind the existing HTTPS proxy.
"""
import argparse
from contextlib import contextmanager
from datetime import date
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
from pydantic import ValidationError
from .personal_models import Upload, PersonalSnapshot
from .analytics import Analytics

MAX_WIRE = 8 * 1024 * 1024
MAX_JSON = 32 * 1024 * 1024


class ServiceError(Exception):
    def __init__(self, status, message, **extra):
        self.status, self.message, self.extra = status, message, extra


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class PersonalStore:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS pairing(hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL,
                created INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS snapshots(device TEXT PRIMARY KEY, sequence INTEGER NOT NULL,
                hash TEXT NOT NULL, payload TEXT NOT NULL, updated INTEGER NOT NULL);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def new_pair(self, ttl=7*86400):
        code = f"{secrets.randbelow(10**12):012d}"
        with self.db() as db:
            db.execute("DELETE FROM pairing WHERE expires < ?", (int(time.time()),))
            db.execute("INSERT INTO pairing VALUES(?,?)", (digest(code), int(time.time())+ttl))
        return code

    def pair(self, code):
        with self.db() as db:
            row = db.execute("SELECT expires FROM pairing WHERE hash=?", (digest(code.strip().upper()),)).fetchone()
            if not row or row["expires"] < int(time.time()):
                raise ServiceError(401, "授权码无效或已过期")
            db.execute("DELETE FROM pairing WHERE hash=?", (digest(code.strip().upper()),))
            device, token = secrets.token_hex(16), secrets.token_urlsafe(32)
            db.execute("INSERT INTO devices(id,token,created) VALUES(?,?,?)", (device,digest(token),int(time.time())))
            return {"deviceId": device, "uploadToken": token}

    def device(self, db, token):
        row = db.execute("SELECT id FROM devices WHERE token=? AND revoked=0", (digest(token),)).fetchone()
        if not row:
            raise ServiceError(401, "设备授权已失效，请重新授权")
        return row["id"]

    def status(self, token):
        with self.db() as db:
            device = self.device(db, token)
            row = db.execute("SELECT sequence,updated FROM snapshots WHERE device=?", (device,)).fetchone()
            return {"deviceId":device,"sequence":row["sequence"] if row else 0,"serverUpdatedAt":row["updated"] if row else None}

    def upload(self, token, value):
        upload = Upload.model_validate(value)
        payload = upload.snapshot.model_dump_json()
        checksum = digest(payload)
        with self.db() as db:
            device = self.device(db, token)
            row = db.execute("SELECT sequence,hash,payload FROM snapshots WHERE device=?", (device,)).fetchone()
            if row:
                if upload.sequence == row["sequence"] and checksum == row["hash"]:
                    return {"sequence":upload.sequence,"duplicate":True}
                if upload.sequence <= row["sequence"]:
                    raise ServiceError(409, "存在更新的快照，请重试", sequence=row["sequence"])
                old = json.loads(row["payload"])
                if old["collectionId"] != upload.snapshot.collectionId:
                    raise ServiceError(409, "词库身份发生变化，请重新授权")
                # Descendant decks can change, but root authorization must stay fixed.
                if (old["mainDeckId"],old["repairDeckId"]) != (upload.snapshot.mainDeckId,upload.snapshot.repairDeckId):
                    raise ServiceError(409, "背词范围改变，请重新授权")
            db.execute("""INSERT INTO snapshots VALUES(?,?,?,?,?) ON CONFLICT(device) DO UPDATE SET
                sequence=excluded.sequence,hash=excluded.hash,payload=excluded.payload,updated=excluded.updated""",
                (device,upload.sequence,checksum,payload,int(time.time()*1000)))
            return {"sequence":upload.sequence,"duplicate":False,"cards":len(upload.snapshot.cards),
                    "reviews":len(upload.snapshot.reviews),"capturedAt":upload.snapshot.capturedAt}

    def remove(self, token):
        with self.db() as db:
            device = self.device(db, token)
            db.execute("DELETE FROM snapshots WHERE device=?", (device,))
            db.execute("UPDATE devices SET revoked=1 WHERE id=?", (device,))
        return {"deleted":True,"revoked":True}

    def query(self, tool, start, end, device=None, limit=50):
        with self.db() as db:
            if device:
                row = db.execute("SELECT * FROM snapshots WHERE device=?", (device,)).fetchone()
            else:
                rows = db.execute("SELECT * FROM snapshots ORDER BY updated DESC LIMIT 2").fetchall()
                if len(rows)>1:
                    raise ValueError("Multiple devices; select device explicitly")
                row = rows[0] if rows else None
            if not row:
                return {"available":False,"reason":"手机还没有上传分析数据"}
            snapshot = PersonalSnapshot.model_validate_json(row["payload"])
            result = Analytics(snapshot).query(tool,start,end,limit=limit)
            result["metadata"].update(sequence=row["sequence"],serverUpdatedAt=row["updated"],deviceId=row["device"])
            return result


def decode_body(raw, encoding):
    if len(raw)>MAX_WIRE:
        raise ServiceError(413,"上传内容过大")
    if encoding == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            data = stream.read(MAX_JSON+1)
    elif not encoding or encoding == "identity":
        data = raw
    else:
        raise ServiceError(415,"不支持的上传格式")
    if len(data)>MAX_JSON:
        raise ServiceError(413,"解压后内容过大")
    return json.loads(data)


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AnkiPersonal/1"
        def log_message(self, fmt, *args):
            # Never log bodies, pairing codes or bearer tokens.
            pass
        def respond(self, status, value):
            body = json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(body)
        def run_request(self):
            self.connection.settimeout(30)
            path = urlsplit(self.path).path
            if self.command=="GET" and path=="/healthz":
                return {"status":"ok","schemaVersion":2}
            token = self.headers.get("Authorization","").removeprefix("Bearer ")
            if self.command=="POST":
                length = int(self.headers.get("Content-Length","-1"))
                if not 0 <= length <= MAX_WIRE:
                    raise ServiceError(413,"上传大小无效")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ServiceError(400,"上传未完成")
                body = decode_body(raw,self.headers.get("Content-Encoding",""))
                if path=="/v1/pair":
                    if not isinstance(body,dict) or set(body)!={"code"} or not isinstance(body["code"],str) or len(body["code"])>32:
                        raise ServiceError(400,"授权码格式无效")
                    return store.pair(body["code"])
                if path=="/v1/snapshot":
                    # Authenticate before parsing the larger schema.
                    store.status(token)
                    return store.upload(token,body)
            if self.command=="GET" and path=="/v1/status":
                return store.status(token)
            if self.command=="DELETE" and path=="/v1/snapshot":
                return store.remove(token)
            raise ServiceError(404,"接口不存在")
        def dispatch(self):
            try:
                self.respond(200,self.run_request())
            except ServiceError as exc:
                self.respond(exc.status,{"error":exc.message,**exc.extra})
            except (ValidationError,ValueError,TypeError,OSError,EOFError):
                self.respond(422,{"error":"数据格式不完整或不符合授权字段范围"})
            except Exception:
                self.respond(500,{"error":"分析服务暂不可用"})
        do_GET = do_POST = do_DELETE = dispatch
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database",default=os.environ.get("ANKI_PERSONAL_DB","personal.sqlite3"))
    parser.add_argument("--port",type=int,default=8766)
    parser.add_argument("--pair",action="store_true")
    parser.add_argument("--query",choices=["get_study_overview","get_daily_reviews","get_difficult_words",
        "get_future_workload","get_deck_statistics","get_repair_progress","get_review_history","get_sync_status"])
    parser.add_argument("--start",type=date.fromisoformat,default=date.today())
    parser.add_argument("--end",type=date.fromisoformat,default=date.today())
    parser.add_argument("--device")
    parser.add_argument("--limit",type=int,default=50)
    args = parser.parse_args()
    store = PersonalStore(args.database)
    if args.pair:
        print(json.dumps({"pairingCode":store.new_pair(),"validDays":7}))
    elif args.query:
        print(json.dumps(store.query(args.query,args.start,args.end,args.device,args.limit),ensure_ascii=False,indent=2))
    else:
        ThreadingHTTPServer(("127.0.0.1",args.port),handler(store)).serve_forever()


if __name__=="__main__":
    main()
