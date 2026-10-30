import copy
from datetime import date
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from server.mcp.analytics import Analytics
from server.mcp.personal_models import PersonalSnapshot
from server.mcp.personal import PersonalStore, ServiceError, decode_body


def fixture():
    return {"sequence":1,"snapshot":{
        "schemaVersion":2,"collectionId":"test-collection","source":"ankidroid-diversion",
        "capturedAt":1793318400000,"zoneId":"Asia/Shanghai","rolloverHour":4,
        "dayIndex":100,"nextDayAt":1793390400,"analysisEnabledAt":1793200000000,
        "scopeDeckIds":[10,20],"mainDeckId":10,"repairDeckId":20,
        "historyAvailable":True,"historyComplete":True,
        "decks":[{"id":10,"name":"English"},{"id":20,"name":"Repair"}],
        "notes":[{"id":1,"word":"interference"}],
        "cards":[{"id":2,"noteId":1,"deckId":20,"queue":2,"due":102,"originalDeckId":0,
            "diversion":{"epoch":1,"again":0,"easy":2,"home":10,"repairAgain":1}}],
        "reviews":[{"id":1793289600000,"cardId":2,"ease":1,"interval":-60,"lastInterval":1,"timeMs":60000,"type":2}],
        "events":[{"reviewId":1793289600000,"cardId":2,"rating":1,"interval":-60,"lastInterval":1,
            "timeMs":60000,"reviewType":2,"deckId":10,"before":"main","after":"repair","interrupted":True,"roundAgain":10}]
    }}


class PersonalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=PersonalStore(Path(self.temp.name)/"personal.sqlite3")
        self.code=self.store.new_pair()
        self.device=self.store.pair(self.code)
        self.token=self.device["uploadToken"]

    def tearDown(self):
        self.temp.cleanup()

    def test_pairing_is_single_use_and_secrets_are_hashed(self):
        with self.assertRaises(ServiceError): self.store.pair(self.code)
        with self.store.db() as db:
            row=db.execute("select token from devices").fetchone()
            self.assertNotEqual(self.token,row["token"])

    def test_repeat_snapshot_does_not_append_reviews(self):
        data=fixture()
        self.store.upload(self.token,data)
        self.assertTrue(self.store.upload(self.token,data)["duplicate"])
        result=self.store.query("get_study_overview",date(2026,10,29),date(2026,10,30))
        self.assertEqual(1,result["data"]["reviews"])

    def test_old_snapshot_cannot_overwrite_new(self):
        data=fixture(); data["sequence"]=2
        self.store.upload(self.token,data)
        with self.assertRaises(ServiceError) as caught: self.store.upload(self.token,fixture())
        self.assertEqual(409,caught.exception.status)
        self.assertEqual(2,self.store.status(self.token)["sequence"])

    def test_incomplete_or_extra_fields_leave_previous_snapshot(self):
        self.store.upload(self.token,fixture())
        bad=fixture(); bad["sequence"]=2; bad["snapshot"]["notes"][0]["Meaning"]="must not upload"
        with self.assertRaises(ValidationError): self.store.upload(self.token,bad)
        bad=fixture(); bad["snapshot"]["cards"]=[]
        with self.assertRaises(ValidationError): self.store.upload(self.token,bad)
        self.assertEqual(1,self.store.status(self.token)["sequence"])

    def test_undo_is_reflected_by_next_complete_snapshot(self):
        self.store.upload(self.token,fixture())
        data=fixture(); data["sequence"]=2; data["snapshot"]["reviews"]=[]; data["snapshot"]["events"]=[]
        self.store.upload(self.token,data)
        result=self.store.query("get_study_overview",date(2026,10,29),date(2026,10,30))
        self.assertEqual(0,result["data"]["reviews"])

    def test_interruption_keeps_again_and_raw_time(self):
        s=PersonalSnapshot.model_validate(fixture()["snapshot"])
        result=Analytics(s).query("get_study_overview",date(2026,10,29),date(2026,10,30))["data"]
        self.assertEqual((1,1,60000,0,1),(result["reviews"],result["again"],result["timeMs"],result["filteredTimeMs"],result["excludedInterrupted"]))

    def test_orphan_or_mismatched_event_is_rejected(self):
        for key,value in [("cardId",999),("rating",4),("timeMs",1),("deckId",99)]:
            data=fixture()["snapshot"]; data["events"][0][key]=value
            with self.assertRaises(ValidationError): PersonalSnapshot.model_validate(data)

    def test_duplicate_ids_and_scope_are_rejected(self):
        for table in ("cards","reviews","notes"):
            data=fixture()["snapshot"]; data[table].append(copy.deepcopy(data[table][0]))
            with self.assertRaises(ValidationError): PersonalSnapshot.model_validate(data)
        data=fixture()["snapshot"]; data["scopeDeckIds"]=[10]
        with self.assertRaises(ValidationError): PersonalSnapshot.model_validate(data)

    def test_credentials_are_isolated_and_deletion_revokes_upload(self):
        with self.assertRaises(ServiceError): self.store.upload("wrong",fixture())
        self.store.upload(self.token,fixture())
        second=self.store.pair(self.store.new_pair())
        self.assertEqual(0,self.store.status(second["uploadToken"])["sequence"])
        self.store.remove(self.token)
        with self.assertRaises(ServiceError): self.store.upload(self.token,fixture())
        self.assertFalse(self.store.query("get_sync_status",date.today(),date.today())["available"])

    def test_gzip_limit_and_incomplete_payload(self):
        data=json.dumps(fixture()).encode()
        self.assertEqual(fixture(),decode_body(gzip.compress(data),"gzip"))
        with patch("server.mcp.personal.MAX_JSON",64):
            with self.assertRaises(ServiceError): decode_body(gzip.compress(b"x"*1000),"gzip")
        with self.assertRaises((EOFError,OSError)): decode_body(gzip.compress(data)[:-5],"gzip")

    def test_native_day_index_works_without_creation_timestamp(self):
        s=PersonalSnapshot.model_validate(fixture()["snapshot"])
        result=Analytics(s).workload(s.capturedAt)
        self.assertTrue(result["available"])
        self.assertEqual(1,result["future"][1]["scheduled"])

    def test_repair_progress_and_rounds_are_explicit(self):
        s=PersonalSnapshot.model_validate(fixture()["snapshot"])
        result=Analytics(s).repair()
        self.assertEqual(2,result["current"][0]["easyStreak"])
        self.assertEqual(10,result["rounds"][0]["mainAgain"])
        self.assertIsNone(result["rounds"][0]["returnedAt"])


if __name__=="__main__": unittest.main()
