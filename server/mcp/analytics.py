"""Deterministic observed metrics, deliberately not an FSRS prediction engine."""
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from .models import Snapshot


class Analytics:
    def __init__(self, snapshot: Snapshot):
        self.s = snapshot
        self.cards = {c.id: c for c in snapshot.cards}
        self.notes = {n.id: n for n in snapshot.notes}

    def day(self, timestamp_ms):
        wall = datetime.fromtimestamp(timestamp_ms/1000, ZoneInfo(self.s.zoneId)).replace(tzinfo=None)
        return (wall - timedelta(hours=self.s.rolloverHour)).date()

    def rows(self, start: date, end: date, deck_id=None):
        return [r for r in self.raw_rows(start,end,deck_id) if r.ease in (1,2,3,4) and r.type in (0,1,2)]

    def raw_rows(self, start: date, end: date, deck_id=None):
        if end < start or (end-start).days > 3660:
            raise ValueError("Invalid date range (maximum 3660 days)")
        return [r for r in self.s.reviews if start <= self.day(r.id) <= end
                and (deck_id is None or (r.cardId in self.cards and self.cards[r.cardId].deckId == deck_id))]

    def metadata(self):
        return {"source": self.s.source, "capturedAt": self.s.capturedAt, "zoneId": self.s.zoneId,
                "rolloverHour": self.s.rolloverHour, "historyAvailable": self.s.historyAvailable,
                "historyComplete": self.s.historyComplete,
                "earliestReviewAt":min((r.id for r in self.s.reviews),default=None),
                "latestReviewAt":max((r.id for r in self.s.reviews),default=None),
                "limitations": self.s.warnings + ["Historical deck filters use current card membership.",
                    "Recorded answer time may be capped by Anki; first observed learning is not guaranteed first-ever learning."]}

    def daily(self, start, end, deck_id=None):
        rows = self.rows(start,end,deck_id)
        grouped = defaultdict(list)
        first = {}
        for r in self.s.reviews:
            c = self.cards.get(r.cardId)
            if c and r.type == 0 and 1 <= r.ease <= 4:
                first[c.noteId] = min(first.get(c.noteId,r.id),r.id)
        for r in rows:
            grouped[self.day(r.id)].append(r)
        results = []
        for offset in range((end-start).days+1):
            day = start + timedelta(days=offset)
            items = grouped[day]
            notes = {self.cards[r.cardId].noteId for r in items if r.cardId in self.cards}
            elapsed = sum(r.timeMs for r in items)
            results.append({"day": day.isoformat(), "reviews":len(items),"distinctCards":len({r.cardId for r in items}),
                "newNotesObserved":sum(n in first and self.day(first[n])==day for n in notes),
                "timeMs":elapsed,"averageMs":elapsed/len(items) if items else None})
        return results

    def retention(self,start,end,deck_id=None):
        all_rows = self.rows(start,end,deck_id)
        rows = [r for r in all_rows if r.type==1]
        def metric(items):
            passed = sum(r.ease>=2 for r in items)
            return {"total":len(items),"passed":passed,"rate":passed/len(items) if items else None}
        return {"definition":"Observed success: ease 2,3,4 / all normal review events (type=1). Not predicted retention.",
            "overall":metric(rows),"young":metric([r for r in rows if r.lastInterval<21]),
            "mature":metric([r for r in rows if r.lastInterval>=21]),
            "stages":{str(stage):dict(Counter(r.ease for r in all_rows if r.type==stage)) for stage in (0,1,2)}}

    def difficult(self,start,end,deck_id=None,sort="again"):
        groups = defaultdict(list)
        for r in self.rows(start,end,deck_id):
            if r.cardId in self.cards:
                groups[self.cards[r.cardId].noteId].append(r)
        result=[]
        for nid, rows in groups.items():
            again=[r for r in rows if r.ease==1]
            if not again:
                continue
            note = self.notes.get(nid)
            result.append({"noteId":nid,"fields":note.fields if note else [],"cardIds":sorted({r.cardId for r in rows}),
                "again":len(again),"lastAgain":max(r.id for r in again),"averageMs":sum(r.timeMs for r in rows)/len(rows),"reviews":len(rows)})
        key={"again":"again","recent":"lastAgain","time":"averageMs","reviews":"reviews"}.get(sort)
        if key is None:
            raise ValueError("Unknown sort")
        return sorted(result,key=lambda v:(-v[key],v["noteId"]))

    def workload(self, now_ms, deck_id=None):
        if self.s.creationSeconds is None:
            return {"available":False,"reason":"Collection creation/day-cutoff metadata is missing"}
        today = self.day(now_ms)
        creation = datetime.fromtimestamp(self.s.creationSeconds,ZoneInfo(self.s.zoneId)).date()
        current = (today-creation).days
        active = [c for c in self.s.cards if c.originalDeckId==0 and c.queue in (1,2,3) and c.due is not None
                  and (deck_id is None or c.deckId==deck_id)]
        return {"available":True,"estimated":True,"due":sum(c.due<= (now_ms//1000 if c.queue==1 else current) for c in active),
                "overdue":sum(c.queue in (2,3) and c.due<current for c in active),
                "future":[{"day":(today+timedelta(days=i)).isoformat(),"scheduled":sum(c.queue in (2,3) and c.due==current+i for c in active)} for i in range(1,31)],
                "limitations":"Snapshot estimate with configured study-day boundary. Excludes filtered cards, new cards, future answers and future new learning."}

    def query(self, tool, start, end, deck_id=None, card_id=None, sort="again", offset=0, limit=100):
        if end < start or (end-start).days > 3660:
            raise ValueError("Invalid date range")
        if offset<0 or not 1<=limit<=500:
            raise ValueError("Invalid pagination")
        meta=self.metadata()
        if tool=="get_future_workload":
            data=self.workload(int(datetime.now(timezone.utc).timestamp()*1000),deck_id)
            if data.get("available"):
                data["future"]=[v for v in data["future"] if start.isoformat()<=v["day"]<=end.isoformat()]
        elif tool=="get_deck_statistics":
            data=[{"deckId":d.id,"name":d.name,"cards":sum(c.deckId==d.id for c in self.s.cards),
                   "queues":dict(Counter(c.queue for c in self.s.cards if c.deckId==d.id))}
                  for d in self.s.decks if deck_id is None or d.id==deck_id]
        elif tool=="get_sync_status":
            data={"capturedAt":self.s.capturedAt,"source":self.s.source}
        elif not self.s.historyAvailable:
            data={"available":False,"reason":"No review log has been imported"}
        elif tool=="get_retention_stats":
            data=self.retention(start,end,deck_id)
        elif tool=="get_difficult_words":
            items=self.difficult(start,end,deck_id,sort)
            data={"items":items[offset:offset+limit],"total":len(items),"offset":offset}
        elif tool=="get_review_history":
            items=sorted((r for r in self.raw_rows(start,end,deck_id) if card_id is None or r.cardId==card_id),key=lambda r:r.id)
            data={"items":[r.model_dump() for r in items[offset:offset+limit]],"total":len(items),"offset":offset}
        elif tool=="get_daily_reviews":
            items=self.daily(start,end,deck_id)
            data={"items":items[offset:offset+limit],"total":len(items),"offset":offset}
        elif tool=="get_study_overview":
            days=self.daily(start,end,deck_id)
            data={"reviews":sum(d["reviews"] for d in days),"timeMs":sum(d["timeMs"] for d in days),
                  "distinctCards":len({r.cardId for r in self.rows(start,end,deck_id)}),
                  "newNotesObserved":sum(d["newNotesObserved"] for d in days),"retention":self.retention(start,end,deck_id)}
        else:
            raise ValueError("Unknown tool")
        return {"data":data,"metadata":meta}
