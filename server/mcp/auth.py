"""Keycloak JWT verification and online introspection; no embedded credentials."""
import asyncio
from dataclasses import dataclass
import os
from urllib.parse import urlparse
import httpx
import jwt
from mcp.server.auth.provider import AccessToken


@dataclass(frozen=True)
class Settings:
    database: str
    public_url: str
    issuer: str
    audience: str
    introspection_client: str
    introspection_secret: str

    @classmethod
    def environment(cls):
        values = {key: os.environ[key] for key in ("DATABASE_URL","PUBLIC_URL","OIDC_ISSUER",
                  "OIDC_AUDIENCE","INTROSPECTION_CLIENT_ID","INTROSPECTION_CLIENT_SECRET")}
        for key in ("PUBLIC_URL","OIDC_ISSUER"):
            u=urlparse(values[key])
            if u.scheme!="https" or not u.netloc or u.username or u.query or u.fragment:
                raise ValueError(f"{key} must be an HTTPS origin/path")
        return cls(values["DATABASE_URL"],values["PUBLIC_URL"].rstrip("/"),values["OIDC_ISSUER"].rstrip("/"),
                   values["OIDC_AUDIENCE"],values["INTROSPECTION_CLIENT_ID"],values["INTROSPECTION_CLIENT_SECRET"])


class OIDCVerifier:
    def __init__(self, settings: Settings):
        self.settings=settings
        self.keys=jwt.PyJWKClient(settings.issuer+"/protocol/openid-connect/certs",timeout=10)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            def decode():
                key=self.keys.get_signing_key_from_jwt(token)
                return jwt.decode(token,key.key,algorithms=["RS256"],audience=self.settings.audience,
                    issuer=self.settings.issuer,options={"require":["exp","iat","sub","iss","aud"]})
            claims=await asyncio.to_thread(decode)
            async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
                response=await client.post(self.settings.issuer+"/protocol/openid-connect/token/introspect",
                    data={"token":token},auth=(self.settings.introspection_client,self.settings.introspection_secret))
                response.raise_for_status()
                if response.json().get("active") is not True:
                    return None
            return AccessToken(token=token,client_id=claims.get("azp", "unknown"),
                scopes=claims.get("scope", "").split(),expires_at=claims["exp"],subject=claims["sub"],claims=claims)
        except (jwt.PyJWTError,httpx.HTTPError,ValueError,KeyError):
            return None
