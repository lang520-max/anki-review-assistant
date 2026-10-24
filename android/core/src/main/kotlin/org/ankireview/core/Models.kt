package org.ankireview.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

val dataJson = Json { ignoreUnknownKeys = true; encodeDefaults = true }

@Serializable data class Deck(val id: Long, val name: String)
@Serializable data class Note(val id: Long, val fields: List<String> = emptyList())
@Serializable data class Card(
    val id: Long, val noteId: Long, val deckId: Long,
    val queue: Int? = null, val type: Int? = null, val due: Long? = null,
    val interval: Int? = null, val reps: Int? = null, val lapses: Int? = null,
    val factor: Int? = null, val originalDeckId: Long = 0,
    val difficulty: Double? = null, val stability: Double? = null,
)
@Serializable data class Review(
    val id: Long, val cardId: Long, val ease: Int, val interval: Int,
    val lastInterval: Int, val timeMs: Long, val type: Int,
)
@Serializable data class Snapshot(
    val schemaVersion: Int = 1, val collectionId: String, val source: String,
    val capturedAt: Long, val zoneId: String, val rolloverHour: Int = 4,
    val creationSeconds: Long? = null, val historyAvailable: Boolean = false,
    val historyComplete: Boolean = false,
    val decks: List<Deck> = emptyList(), val notes: List<Note> = emptyList(),
    val cards: List<Card> = emptyList(), val reviews: List<Review> = emptyList(),
    val warnings: List<String> = emptyList(),
)
