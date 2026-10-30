"""Single-owner OAuth for the private ChatGPT plugin; independent of phone upload keys."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlparse

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    RefreshToken, RegistrationError, TokenError, construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

SCOPE = "study:read"
OWNER = "personal-owner"
CHATGPT_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


class PersonalOAuth:
    def __init__(self, database, issuer, callbacks=(CHATGPT_CALLBACK,)):
        self.database = str(database)
        self.issuer = issuer.rstrip("/")
        self.resource = self.issuer + "/mcp"
        self.callbacks = set(callbacks)
        if urlparse(self.issuer).scheme != "https":
            raise ValueError("Public plugin requires HTTPS")
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS oauth_clients(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS login_codes(hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS pending_login(id TEXT PRIMARY KEY, data TEXT NOT NULL,
                    expires INTEGER NOT NULL, csrf TEXT);
                CREATE TABLE IF NOT EXISTS oauth_codes(hash TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS oauth_tokens(hash TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    family TEXT NOT NULL, data TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=15)
        try:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def new_login(self):
        code = f"{secrets.randbelow(10**16):016d}"
        with self.db() as db:
            db.execute("DELETE FROM login_codes WHERE expires < ?", (int(time.time()),))
            db.execute("INSERT INTO login_codes VALUES(?,?)", (hashed(code), int(time.time())+7*86400))
        return code

    def revoke_all(self):
        with self.db() as db:
            for table in ("oauth_tokens", "oauth_codes", "pending_login", "login_codes"):
                db.execute(f"DELETE FROM {table}")

    async def get_client(self, client_id):
        with self.db() as db:
            row = db.execute("SELECT data FROM oauth_clients WHERE id=?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(row[0]) if row else None

    async def register_client(self, client_info):
        redirects = {str(u) for u in client_info.redirect_uris or []}
        if not redirects or not redirects <= self.callbacks:
            raise RegistrationError("invalid_redirect_uri", "Use the exact approved ChatGPT callback")
        if (client_info.token_endpoint_auth_method not in ("none", "client_secret_post", "client_secret_basic")
                or set(client_info.grant_types) - {"authorization_code", "refresh_token"}
                or client_info.response_types != ["code"]
                or set((client_info.scope or SCOPE).split()) != {SCOPE}):
            raise RegistrationError("invalid_client_metadata", "Only read-only authorization-code + PKCE is supported")
        with self.db() as db:
            if db.execute("SELECT count(*) FROM oauth_clients").fetchone()[0] >= 1000:
                raise RegistrationError("invalid_client_metadata", "Registration capacity reached")
            db.execute("INSERT INTO oauth_clients VALUES(?,?)", (client_info.client_id, client_info.model_dump_json()))

    async def authorize(self, client, params: AuthorizationParams):
        if (params.resource != self.resource or set(params.scopes or [SCOPE]) != {SCOPE}
                or str(params.redirect_uri) not in self.callbacks):
            raise AuthorizeError("invalid_request", "Invalid resource, scope or callback")
        flow = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("DELETE FROM pending_login WHERE expires < ?", (int(time.time()),))
            data = {"client": client.client_id, "params": params.model_dump(mode="json")}
            db.execute("INSERT INTO pending_login VALUES(?,?,?,NULL)",
                       (flow, json.dumps(data), int(time.time())+600))
        return self.issuer + "/connect?flow=" + flow

    def login_page(self, flow, csrf):
        with self.db() as db:
            row = db.execute("SELECT data FROM pending_login WHERE id=? AND expires>=?",
                             (flow, int(time.time()))).fetchone()
            if not row:
                raise ValueError("连接请求已过期，请回 ChatGPT 重新连接")
            db.execute("UPDATE pending_login SET csrf=? WHERE id=?", (hashed(csrf), flow))
        return json.loads(row[0])

    def approve(self, flow, csrf, login_code):
        with self.db() as db:
            row = db.execute("SELECT * FROM pending_login WHERE id=? AND expires>=?",
                             (flow, int(time.time()))).fetchone()
            if not row or not row["csrf"] or not secrets.compare_digest(row["csrf"], hashed(csrf)):
                raise ValueError("连接页面已过期，请回 ChatGPT 重新连接")
            secret = hashed(login_code.strip())
            login = db.execute("SELECT expires FROM login_codes WHERE hash=?", (secret,)).fetchone()
            if not login or login[0] < int(time.time()):
                raise ValueError("私人连接码无效或已使用，请核对后重新连接")
            data = json.loads(row["data"])
            params = AuthorizationParams.model_validate(data["params"])
            code = AuthorizationCode(code="", scopes=[SCOPE], expires_at=time.time()+180,
                client_id=data["client"], code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri, redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=self.resource, subject=OWNER)
            raw = secrets.token_urlsafe(32)
            db.execute("INSERT INTO oauth_codes VALUES(?,?)", (hashed(raw), code.model_dump_json()))
            db.execute("DELETE FROM login_codes WHERE hash=?", (secret,))
            db.execute("DELETE FROM pending_login WHERE id=?", (flow,))
        return construct_redirect_uri(str(params.redirect_uri), code=raw, state=params.state, iss=self.issuer)

    async def load_authorization_code(self, client, authorization_code):
        with self.db() as db:
            row = db.execute("SELECT data FROM oauth_codes WHERE hash=?", (hashed(authorization_code),)).fetchone()
        if not row:
            return None
        value = AuthorizationCode.model_validate_json(row[0])
        if value.client_id != client.client_id or value.expires_at < time.time():
            return None
        return value.model_copy(update={"code": authorization_code})

    def issue(self, db, client_id, family):
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        now = int(time.time())
        a = AccessToken(token="", client_id=client_id, scopes=[SCOPE], expires_at=now+900,
                        resource=self.resource, subject=OWNER, claims={"iss":self.issuer})
        r = RefreshToken(token="", client_id=client_id, scopes=[SCOPE], expires_at=now+90*86400, subject=OWNER)
        db.execute("INSERT INTO oauth_tokens(hash,kind,family,data) VALUES(?,?,?,?)",
                   (hashed(access), "access", family, a.model_dump_json()))
        db.execute("INSERT INTO oauth_tokens(hash,kind,family,data) VALUES(?,?,?,?)",
                   (hashed(refresh), "refresh", family, r.model_dump_json()))
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=900,
                          refresh_token=refresh, scope=SCOPE)

    async def exchange_authorization_code(self, client, authorization_code):
        with self.db() as db:
            row = db.execute("SELECT data FROM oauth_codes WHERE hash=?", (hashed(authorization_code.code),)).fetchone()
            if not row:
                raise TokenError("invalid_grant", "Code already used")
            value = AuthorizationCode.model_validate_json(row[0])
            if value.expires_at < time.time() or value.client_id != client.client_id or value.resource != self.resource:
                raise TokenError("invalid_grant", "Invalid authorization")
            db.execute("DELETE FROM oauth_codes WHERE hash=?", (hashed(authorization_code.code),))
            return self.issue(db, client.client_id, secrets.token_hex(16))

    async def load_refresh_token(self, client, refresh_token):
        with self.db() as db:
            row = db.execute("SELECT * FROM oauth_tokens WHERE hash=? AND kind='refresh'", (hashed(refresh_token),)).fetchone()
            if not row:
                return None
            value = RefreshToken.model_validate_json(row["data"])
            if value.client_id != client.client_id:
                return None
            if row["used"]:
                # A consumed refresh token was replayed. Revoke the entire link.
                db.execute("DELETE FROM oauth_tokens WHERE family=?", (row["family"],))
                return None
            if value.expires_at < time.time():
                return None
        return value.model_copy(update={"token":refresh_token})

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        with self.db() as db:
            row = db.execute("SELECT * FROM oauth_tokens WHERE hash=? AND kind='refresh' AND used=0",
                             (hashed(refresh_token.token),)).fetchone()
            if (not row or refresh_token.client_id != client.client_id or refresh_token.expires_at < time.time()
                    or set(scopes) != {SCOPE}):
                raise TokenError("invalid_grant", "Invalid refresh authorization")
            db.execute("UPDATE oauth_tokens SET used=1 WHERE hash=?", (hashed(refresh_token.token),))
            db.execute("DELETE FROM oauth_tokens WHERE family=? AND kind='access'", (row["family"],))
            return self.issue(db, client.client_id, row["family"])

    async def load_access_token(self, token):
        with self.db() as db:
            row = db.execute("SELECT data FROM oauth_tokens WHERE hash=? AND kind='access' AND used=0", (hashed(token),)).fetchone()
        if not row:
            return None
        value = AccessToken.model_validate_json(row[0])
        if (value.expires_at < time.time() or value.resource != self.resource
                or value.subject != OWNER or value.claims != {"iss":self.issuer} or value.scopes != [SCOPE]):
            return None
        return value.model_copy(update={"token":token})

    async def revoke_token(self, token):
        with self.db() as db:
            row = db.execute("SELECT family FROM oauth_tokens WHERE hash=?", (hashed(token.token),)).fetchone()
            if row:
                db.execute("DELETE FROM oauth_tokens WHERE family=?", (row[0],))
