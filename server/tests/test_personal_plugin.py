import asyncio
import base64
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient
from server.mcp.personal import PersonalStore
from server.mcp.personal_oauth import PersonalOAuth, CHATGPT_CALLBACK, SCOPE, hashed
from server.mcp.personal_plugin import create_app, SnapshotReader, TOOLS
from server.tests.test_personal import fixture

BASE = "https://plugin.example"
ISSUER = BASE+"/anki-plugin"
RESOURCE = ISSUER+"/mcp"


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.provider = PersonalOAuth(self.path/"auth.sqlite3",ISSUER)
        self.store = PersonalStore(self.path/"data.sqlite3")
        self.device = self.store.pair(self.store.new_pair())
        self.store.upload(self.device["uploadToken"],fixture())
        self.client = TestClient(create_app(self.provider,self.path/"data.sqlite3"),base_url=BASE)
        self.client.__enter__()
        self.verifier = "a"*64
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip("=")
        self.registered = self.client.post("/anki-plugin/register",json={
            "client_name":"ChatGPT","redirect_uris":[CHATGPT_CALLBACK],
            "token_endpoint_auth_method":"none","grant_types":["authorization_code","refresh_token"],
            "response_types":["code"],"scope":SCOPE}).json()
        self.cid = self.registered["client_id"]

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def start(self, **overrides):
        values = dict(client_id=self.cid,redirect_uri=CHATGPT_CALLBACK,response_type="code",
                      scope=SCOPE,state="test-state",code_challenge=self.challenge,
                      code_challenge_method="S256",resource=RESOURCE)
        values.update(overrides)
        response = self.client.get("/anki-plugin/authorize",params=values,follow_redirects=False)
        return response

    def consent(self):
        response = self.start()
        self.assertEqual(302,response.status_code)
        uri = response.headers["location"]
        page = self.client.get(uri)
        self.assertEqual(200,page.status_code)
        self.assertEqual("same-origin",page.headers["referrer-policy"])
        self.assertIn("form-action 'self' https://chatgpt.com;",page.headers["content-security-policy"])
        form = {key:re.search(r'name="'+key+r'" value="([^"]+)"',page.text).group(1) for key in ("csrf","flow")}
        return form

    def code(self):
        form = self.consent()
        form["code"] = self.provider.new_login()
        response = self.client.post("/anki-plugin/connect",data=form,follow_redirects=False)
        self.assertEqual(303,response.status_code,response.text)
        values = parse_qs(urlparse(response.headers["location"]).query)
        self.assertEqual([ISSUER],values["iss"])
        self.assertEqual(["test-state"],values["state"])
        return values["code"][0]

    def exchange(self, code, verifier=None, **other):
        return self.client.post("/anki-plugin/token",data={
            "grant_type":"authorization_code","client_id":self.cid,"code":code,
            "redirect_uri":CHATGPT_CALLBACK,"code_verifier":verifier or self.verifier,
            "resource":RESOURCE,**other})

    def tokens(self):
        response = self.exchange(self.code())
        self.assertEqual(200,response.status_code,response.text)
        return response.json()

    def rpc(self, token, method, params=None):
        return self.client.post("/anki-plugin/mcp",headers={
            "Authorization":"Bearer "+token,"Accept":"application/json, text/event-stream"},
            json={"jsonrpc":"2.0","id":1,"method":method,"params":params or {}})

    def test_metadata_and_anonymous_protection(self):
        response = self.rpc("invalid","tools/list")
        self.assertEqual(401,response.status_code)
        self.assertIn("/.well-known/oauth-protected-resource/anki-plugin/mcp",response.headers["www-authenticate"])
        meta = self.client.get("/.well-known/oauth-protected-resource/anki-plugin/mcp").json()
        self.assertEqual(RESOURCE,meta["resource"])
        self.assertEqual([ISSUER],meta["authorization_servers"])
        meta = self.client.get("/.well-known/oauth-authorization-server/anki-plugin").json()
        self.assertTrue(meta["authorization_response_iss_parameter_supported"])
        self.assertIn("S256",meta["code_challenge_methods_supported"])
        self.assertIn("none",meta["token_endpoint_auth_methods_supported"])

    def test_unapproved_redirect_and_write_scopes_are_rejected(self):
        response = self.client.post("/anki-plugin/register",json={"redirect_uris":["https://attacker.example/callback"]})
        self.assertEqual(400,response.status_code)
        response = self.start(scope="study:delete")
        self.assertNotIn("/connect?flow",response.headers.get("location", ""))
        response = self.start(resource="https://other.example/mcp")
        self.assertNotIn("/connect?flow",response.headers.get("location", ""))

    def test_csrf_and_invalid_login_do_not_consume_code(self):
        form = self.consent(); secret = self.provider.new_login()
        response = self.client.post("/anki-plugin/connect",data={**form,"csrf":"wrong","code":secret})
        self.assertEqual(403,response.status_code)
        response = self.client.post("/anki-plugin/connect",data={**form,"code":"0"*16})
        self.assertEqual(400,response.status_code)
        response = self.client.post("/anki-plugin/connect",data={**form,"code":secret},follow_redirects=False)
        self.assertEqual(303,response.status_code)
        second = self.consent()
        self.assertEqual(400,self.client.post("/anki-plugin/connect",data={**second,"code":secret}).status_code)

    def test_pkce_resource_and_single_use_code(self):
        code = self.code()
        self.assertEqual(400,self.exchange(code,verifier="b"*64).status_code)
        self.assertEqual(400,self.exchange(code,resource="https://other.example/mcp").status_code)
        response = self.exchange(code)
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(400,self.exchange(code).status_code)

    def test_read_tools_use_real_snapshot_and_have_no_writes(self):
        token = self.tokens()["access_token"]
        response = self.rpc(token,"tools/list")
        self.assertEqual(200,response.status_code,response.text)
        tools = response.json()["result"]["tools"]
        self.assertEqual(set(TOOLS),{t["name"] for t in tools})
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
        response = self.rpc(token,"tools/call",{"name":"get_repair_progress","arguments":{
            "start_date":"2026-10-29","end_date":"2026-10-30"}})
        result = response.json()["result"]
        self.assertFalse(result.get("isError",False),result)
        data = result["structuredContent"]
        self.assertEqual("interference",data["data"]["current"][0]["word"])
        self.assertEqual(2,data["data"]["current"][0]["easyStreak"])
        self.assertEqual(401,self.rpc(self.device["uploadToken"],"tools/list").status_code)
        # Plugin bearer token cannot mutate or replace the phone snapshot.
        self.assertEqual(404,self.client.post("/anki-plugin/v1/snapshot",json={}).status_code)

    def test_refresh_rotation_replay_and_revoke(self):
        tokens = self.tokens()
        data = {"grant_type":"refresh_token","client_id":self.cid,"refresh_token":tokens["refresh_token"],"resource":RESOURCE}
        refreshed = self.client.post("/anki-plugin/token",data=data)
        self.assertEqual(200,refreshed.status_code,refreshed.text)
        current = refreshed.json()
        self.assertEqual(401,self.rpc(tokens["access_token"],"tools/list").status_code)
        self.assertEqual(200,self.rpc(current["access_token"],"tools/list").status_code)
        self.assertEqual(400,self.client.post("/anki-plugin/token",data=data).status_code)
        self.assertEqual(401,self.rpc(current["access_token"],"tools/list").status_code)
        tokens = self.tokens()
        response = self.client.post("/anki-plugin/revoke",data={"client_id":self.cid,"token":tokens["refresh_token"]})
        self.assertEqual(200,response.status_code,response.text)
        self.assertEqual(401,self.rpc(tokens["access_token"],"tools/list").status_code)

    def test_restart_preserves_credentials_and_tokens_are_hashed(self):
        tokens = self.tokens()
        fresh = PersonalOAuth(self.path/"auth.sqlite3",ISSUER)
        self.assertIsNotNone(asyncio.run(fresh.load_access_token(tokens["access_token"])))
        with fresh.db() as db:
            stored = str([tuple(row) for row in db.execute("SELECT * FROM oauth_tokens")])
        self.assertNotIn(tokens["access_token"],stored)
        self.assertNotIn(tokens["refresh_token"],stored)
        fresh.revoke_all()
        self.assertIsNone(asyncio.run(fresh.load_access_token(tokens["access_token"])))
        self.assertEqual(1,self.store.status(self.device["uploadToken"])["sequence"])

    def test_empty_snapshot_and_multiple_devices_are_explicit(self):
        token = self.tokens()["access_token"]
        self.store.remove(self.device["uploadToken"])
        response = self.rpc(token,"tools/call",{"name":"get_sync_status","arguments":{
            "start_date":"2026-10-29","end_date":"2026-10-30"}})
        self.assertFalse(response.json()["result"]["structuredContent"]["available"])
        for _ in range(2):
            new = self.store.pair(self.store.new_pair())
            self.store.upload(new["uploadToken"],fixture())
        reader = SnapshotReader(self.path/"data.sqlite3")
        result = reader.query("get_sync_status",date(2026,10,29),date(2026,10,30))
        self.assertFalse(result["available"])
        self.assertEqual(2,len(result["devices"]))


if __name__=="__main__":
    unittest.main()
