import os
import unittest
import uuid
from server.mcp.storage import Store, Conflict
from server.mcp.models import SyncBatch
from server.tests.test_service import fixture


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"),"PostgreSQL integration runs in Actions service container")
class PostgresTests(unittest.TestCase):
    def test_postgres_transaction_and_tombstone(self):
        store=Store(os.environ["TEST_DATABASE_URL"])
        owner=str(uuid.uuid4())
        batch=SyncBatch(baseRevision=0,batchId="a"*64,snapshot=fixture())
        self.assertEqual(store.sync(owner,"fixture",batch)["revision"],1)
        self.assertTrue(store.sync(owner,"fixture",batch)["duplicate"])
        store.delete(owner,"fixture")
        with self.assertRaises(Conflict): store.sync(owner,"fixture",batch)
