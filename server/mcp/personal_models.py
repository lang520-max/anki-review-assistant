"""Strict, word-only schema for the integrated AnkiDroid personal upload route."""
from typing import Literal
from pydantic import Field, model_validator
from .models import Model, Card, Review, Snapshot


class WordNote(Model):
    id: int = Field(gt=0)
    word: str = Field(default="", max_length=512)

    @property
    def fields(self):
        return [self.word] if self.word else []


class DiversionProgress(Model):
    epoch: int = Field(ge=0)
    again: int = Field(ge=0, le=9)
    easy: int = Field(ge=0, le=5)
    home: int = Field(ge=0)
    repairAgain: int = Field(ge=0)


class PersonalCard(Card):
    diversion: DiversionProgress | None = None


class AnswerEvent(Model):
    reviewId: int = Field(gt=0)
    cardId: int = Field(gt=0)
    rating: int = Field(ge=1, le=4)
    timeMs: int = Field(ge=0, le=86400000)
    interval: int
    lastInterval: int
    reviewType: int
    deckId: int = Field(gt=0)
    before: Literal["main", "repair", "other"]
    after: Literal["main", "repair", "other"]
    interrupted: bool = False
    roundAgain: int = Field(ge=0)


class PersonalSnapshot(Snapshot):
    schemaVersion: Literal[2] = 2
    source: Literal["ankidroid-diversion"] = "ankidroid-diversion"
    notes: list[WordNote] = Field(default_factory=list, max_length=100000)
    cards: list[PersonalCard] = Field(default_factory=list, max_length=200000)
    events: list[AnswerEvent] = Field(default_factory=list, max_length=1000000)
    dayIndex: int = Field(ge=0)
    nextDayAt: int = Field(gt=0)
    analysisEnabledAt: int = Field(ge=0)
    scopeDeckIds: list[int] = Field(min_length=1, max_length=10000)
    mainDeckId: int = Field(gt=0)
    repairDeckId: int = Field(gt=0)

    @model_validator(mode="after")
    def references(self):
        decks = {d.id for d in self.decks}
        notes = {n.id for n in self.notes}
        cards = {c.id: c for c in self.cards}
        reviews = {r.id: r for r in self.reviews}
        scope = set(self.scopeDeckIds)
        if len(scope) != len(self.scopeDeckIds) or scope != decks:
            raise ValueError("Deck scope mismatch")
        if not {self.mainDeckId, self.repairDeckId} <= scope:
            raise ValueError("Rule decks absent")
        if any(c.noteId not in notes or (c.originalDeckId or c.deckId) not in scope for c in self.cards):
            raise ValueError("Card outside scope or note missing")
        if notes != {c.noteId for c in self.cards}:
            raise ValueError("Unreferenced notes")
        if any(r.cardId not in cards for r in self.reviews):
            raise ValueError("Orphan review")
        if len({e.reviewId for e in self.events}) != len(self.events):
            raise ValueError("Duplicate event")
        for e in self.events:
            r = reviews.get(e.reviewId)
            if r is None or (e.cardId,e.rating,e.timeMs,e.interval,e.lastInterval,e.reviewType) != (
                    r.cardId,r.ease,r.timeMs,r.interval,r.lastInterval,r.type):
                raise ValueError("Event does not match live review")
            if e.deckId not in scope:
                raise ValueError("Event deck outside scope")
        return self


class Upload(Model):
    sequence: int = Field(gt=0, le=9223372036854775807)
    snapshot: PersonalSnapshot
