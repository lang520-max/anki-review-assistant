import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from server.mcp.auth import OIDCVerifier, Settings


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ephemeral synthetic key, never written to disk or committed.
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.settings=Settings("unused","https://study.example","https://auth.example/realms/anki","anki-review","service","synthetic-placeholder")
        self.verifier=OIDCVerifier(self.settings)
        self.verifier.keys=SimpleNamespace(get_signing_key_from_jwt=lambda _:SimpleNamespace(key=self.key.public_key()))
    def token(self,**changes):
        claims={"sub":"synthetic-user","iss":self.settings.issuer,"aud":self.settings.audience,
                "iat":int(time.time()),"exp":int(time.time())+300,"scope":"study:read","azp":"synthetic-client"}
        claims.update(changes)
        return jwt.encode(claims,self.key,algorithm="RS256")
    def check(self,token,active=True):
        response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{"active":active})
        client=AsyncMock();client.post.return_value=response
        with patch("server.mcp.auth.asyncio.to_thread",new=AsyncMock(side_effect=lambda fn:fn())), \
             patch("server.mcp.auth.httpx.AsyncClient") as constructor:
            constructor.return_value.__aenter__.return_value=client
            return asyncio.run(self.verifier.verify_token(token))
    def test_valid_signature_subject_and_scope(self):
        token=self.check(self.token())
        self.assertEqual(token.subject,"synthetic-user")
        self.assertEqual(token.scopes,["study:read"])
    def test_wrong_audience_issuer_expiry_or_signature_fails(self):
        for changes in ({"aud":"another-service"},{"iss":"https://wrong.example"},{"exp":0}):
            self.assertIsNone(self.check(self.token(**changes)))
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        bad=jwt.encode({"sub":"synthetic"},other,algorithm="RS256")
        self.assertIsNone(self.check(bad))
    def test_revocation_fails_closed(self):
        self.assertIsNone(self.check(self.token(),active=False))
