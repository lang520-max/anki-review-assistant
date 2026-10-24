import asyncio
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
import httpx
from mcp.server.auth.provider import AccessToken
from server.mcp.models import Snapshot, SyncBatch
from server.mcp.storage import Store, Conflict
from server.mcp.analytics import Analytics
from server.mcp.auth import Settings
from server.mcp.app import create_app, TOOL_NAMES


def timestamp(value):
    return int(datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()*1000)


def fixture():
    return Snapshot.model_validate({"collectionId":"fixture","source":"synthetic","capturedAt":0,"zoneId":"UTC",
        "historyAvailable":True,"decks":[{"id":100,"name":"Synthetic"}],"notes":[{"id":10,"fields":["synthetic word"]}],
        "cards":[{"id":1,"noteId":10,"deckId":100},{"id":2,"noteId":10,"deckId":100}],
        "reviews":[{"id":timestamp("2026-01-01T12:00:00Z")+i,"cardId":1 if i%2==0 else 2,
            "ease":ease,"interval":30,"lastInterval":last,"timeMs":1000+i*100,"type":stage}
            for i,(ease,last,stage) in enumerate([(2,21,1),(1,10,0),(1,30,1),(4,30,4)])]})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store=Store(str(Path(self.directory.name)/"test.db"))
        self.snapshot=fixture()
    def batch(self,revision=0,key="a",snapshot=None):
        return SyncBatch(baseRevision=revision,batchId=key*64,snapshot=snapshot or self.snapshot)
    def test_idempotence_and_owner_isolation(self):
        self.assertEqual(self.store.sync("alice","fixture",self.batch())["revision"],1)
        self.assertTrue(self.store.sync("alice","fixture",self.batch())["duplicate"])
        with self.assertRaises(KeyError):
            self.store.get("bob","fixture")
        self.assertEqual(self.store.status("bob"),[])
    def test_stale_update_cannot_resurrect_deleted_data(self):
        self.store.sync("alice","fixture",self.batch())
        self.assertEqual(self.store.delete("alice","fixture")["revision"],2)
        with self.assertRaises(Conflict):
            self.store.sync("alice","fixture",self.batch(1,"b"))
        with self.assertRaises(KeyError):
            self.store.get("alice","fixture")
    def test_incremental_removal_updates_and_reimport(self):
        self.store.sync("alice","fixture",self.batch())
        metadata=self.snapshot.model_dump(exclude={"decks","notes","cards","reviews"})
        batch=SyncBatch(baseRevision=1,batchId="b"*64,metadata=metadata,
            deletes={"reviews":[self.snapshot.reviews[0].id]})
        self.store.sync("alice","fixture",batch)
        self.assertEqual(len(self.store.get("alice","fixture").reviews),3)
        self.store.sync("alice","fixture",self.batch(2,"c",self.snapshot.model_copy(update={"reviews":[]})))
        self.assertEqual(self.store.get("alice","fixture").reviews,[])
    def test_metrics_hard_is_success_and_manual_is_excluded(self):
        a=Analytics(self.snapshot); d=date(2026,1,1)
        r=a.retention(d,d)
        self.assertEqual(r["overall"],{"total":2,"passed":1,"rate":.5})
        self.assertEqual(a.daily(d,d)[0]["reviews"],3)
        self.assertEqual(len(a.difficult(d,d)),1)
        self.assertEqual(a.difficult(d,d)[0]["again"],2)
    def test_dst_and_study_day(self):
        a=Analytics(self.snapshot.model_copy(update={"zoneId":"America/New_York"}))
        self.assertEqual(a.day(timestamp("2026-03-08T07:30:00Z")),date(2026,3,7))
        self.assertEqual(a.day(timestamp("2026-03-08T08:00:00Z")),date(2026,3,8))
    def test_no_history_and_no_denominator_are_not_zero(self):
        s=self.snapshot.model_copy(update={"historyAvailable":False,"reviews":[]})
        d=date(2026,1,1); a=Analytics(s)
        self.assertFalse(a.query("get_study_overview",d,d)["data"]["available"])
        self.assertIsNone(a.retention(d,d)["overall"]["rate"])
        self.assertFalse(a.workload(0)["available"])
    def test_all_eight_queries_and_limits(self):
        a=Analytics(self.snapshot); d=date(2026,1,1)
        for name in TOOL_NAMES:
            self.assertIn("metadata",a.query(name,d,d))
        with self.assertRaises(ValueError): a.query("get_review_history",d,d,limit=501)
        with self.assertRaises(ValueError): a.rows(d,date(2025,1,1))
    def test_duplicate_ids_and_bad_zone_rejected(self):
        data=self.snapshot.model_dump(); data["reviews"].append(data["reviews"][0])
        with self.assertRaises(ValueError): Snapshot.model_validate(data)
        data["reviews"]=[]; data["zoneId"]="bad"
        with self.assertRaises(ValueError): Snapshot.model_validate(data)
    def test_http_auth_scopes_and_owner_binding(self):
        class Verifier:
            async def verify_token(self,token):
                if token=="invalid": return None
                return AccessToken(token=token,client_id="test",subject=token,
                    scopes=["study:read"] if token=="reader" else ["study:read","study:sync","study:delete"])
        app=create_app(Settings("unused","https://study.example","https://auth.example/realms/anki","anki","test","unused-test-placeholder"),Verifier(),self.store)
        async def scenario():
            # Keep ASGI tests progressing on runners that restrict loop wakeup sockets.
            async def heartbeat():
                while True:
                    await asyncio.sleep(0.01)
            tick=asyncio.create_task(heartbeat())
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://study.example") as client:
                    self.assertEqual((await client.get("/v1/collections")).status_code,401)
                    self.assertEqual((await client.get("/v1/collections",headers={"Authorization":"Bearer invalid"})).status_code,401)
                    body=self.batch().model_dump(mode="json")
                    self.assertEqual((await client.post("/v1/collections/fixture/sync",json=body,headers={"Authorization":"Bearer reader"})).status_code,403)
                    self.assertEqual((await client.post("/v1/collections/fixture/sync",json=body,headers={"Authorization":"Bearer alice"})).status_code,200)
                    result=await client.get("/v1/collections",headers={"Authorization":"Bearer bob"})
                    self.assertEqual(result.json()["collections"],[])
                    headers={"Authorization":"Bearer alice","Accept":"application/json, text/event-stream"}
                    result=await client.post("/mcp",headers=headers,json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{
                        "protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"tests","version":"1"}}})
                    self.assertEqual(result.status_code,200,result.text)
                    result=await client.post("/mcp",headers={**headers,"MCP-Protocol-Version":"2025-11-25"},
                        json={"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
                    self.assertEqual(result.status_code,200,result.text)
                    tools=result.json()["result"]["tools"]
                    self.assertEqual({t["name"] for t in tools},set(TOOL_NAMES))
                    self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
                    call={"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_study_overview",
                        "arguments":{"collection_id":"fixture","start_date":"2026-01-01","end_date":"2026-01-01"}}}
                    result=await client.post("/mcp",headers={**headers,"MCP-Protocol-Version":"2025-11-25"},json=call)
                    self.assertIn("structuredContent", result.json()["result"], result.text)
                    self.assertEqual(result.json()["result"]["structuredContent"]["data"]["reviews"],3)
                    result=await client.post("/mcp",headers={**headers,"Authorization":"Bearer bob","MCP-Protocol-Version":"2025-11-25"},json=call)
                    self.assertTrue(result.json()["result"]["isError"])
                    call["params"]["name"]="get_sync_status"
                    result=await client.post("/mcp",headers={**headers,"MCP-Protocol-Version":"2025-11-25"},json=call)
                    status=result.json()["result"]["structuredContent"]["data"]
                    self.assertEqual(status["revision"],1)
                    self.assertGreater(status["serverSyncedAt"],0)
                    self.assertEqual((await client.delete("/v1/collections/fixture",headers={"Authorization":"Bearer reader"})).status_code,403)
            tick.cancel()
        asyncio.run(scenario())


if __name__=="__main__":
    unittest.main()
