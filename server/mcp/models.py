"""Versioned Android JSON exchange; IDs stay integers (do not pass through JS floats)."""
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Deck(Model):
    id: int = Field(gt=0)
    name: str = Field(max_length=4096)


class Note(Model):
    id: int = Field(gt=0)
    fields: list[str] = Field(default_factory=list, max_length=1000)


class Card(Model):
    id: int = Field(gt=0)
    noteId: int = Field(gt=0)
    deckId: int = Field(gt=0)
    queue: int | None = None
    type: int | None = None
    due: int | None = None
    interval: int | None = None
    reps: int | None = None
    lapses: int | None = None
    factor: int | None = None
    originalDeckId: int = 0
    difficulty: float | None = None
    stability: float | None = None


class Review(Model):
    id: int = Field(gt=0, le=253402300799999)
    cardId: int = Field(gt=0)
    ease: int
    interval: int
    lastInterval: int
    timeMs: int = Field(ge=0, le=86400000)
    type: int


class Snapshot(Model):
    schemaVersion: Literal[1] = 1
    collectionId: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    source: str = Field(max_length=100)
    capturedAt: int = Field(ge=0)
    zoneId: str
    rolloverHour: int = Field(default=4, ge=0, le=23)
    creationSeconds: int | None = None
    historyAvailable: bool = False
    historyComplete: bool = False
    decks: list[Deck] = Field(default_factory=list, max_length=10000)
    notes: list[Note] = Field(default_factory=list, max_length=100000)
    cards: list[Card] = Field(default_factory=list, max_length=200000)
    reviews: list[Review] = Field(default_factory=list, max_length=1000000)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("zoneId")
    @classmethod
    def zone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, KeyError):
            raise ValueError("Unknown IANA timezone") from None
        return value

    @model_validator(mode="after")
    def unique_ids(self):
        for table in (self.decks, self.notes, self.cards, self.reviews):
            if len({row.id for row in table}) != len(table):
                raise ValueError("Duplicate entity IDs")
        return self


class SyncBatch(Model):
    baseRevision: int = Field(ge=0)
    batchId: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot: Snapshot | None = None
    # Incremental updates carry metadata separately from keyed rows.
    metadata: dict | None = None
    upserts: dict[str, list[dict]] = Field(default_factory=dict)
    deletes: dict[str, list[int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def one_format(self):
        if (self.snapshot is None) == (self.metadata is None):
            raise ValueError("Provide exactly one of snapshot or metadata")
        allowed = {"decks", "notes", "cards", "reviews"}
        if set(self.upserts) - allowed or set(self.deletes) - allowed:
            raise ValueError("Unknown entity table")
        return self
