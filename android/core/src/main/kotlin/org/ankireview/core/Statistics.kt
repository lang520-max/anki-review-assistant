package org.ankireview.core

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

data class Daily(val day: LocalDate, val reviews: Int, val distinctCards: Int, val newNotesObserved: Int,
                 val timeMs: Long, val averageMs: Double?)
data class Retention(val reviewed: Int, val passed: Int, val youngTotal: Int, val youngPassed: Int,
                     val matureTotal: Int, val maturePassed: Int) {
    val rate: Double? get() = if (reviewed == 0) null else passed.toDouble() / reviewed
}
data class Difficult(val noteId: Long, val word: String, val cardIds: List<Long>, val again: Int,
                     val lastAgain: Long?, val averageMs: Double, val total: Int)
enum class WordSort { AGAIN, RECENT, TIME, REVIEWS }

class Statistics(val snapshot: Snapshot) {
    private val zone = ZoneId.of(snapshot.zoneId)
    private val cardMap = snapshot.cards.associateBy { it.id }
    // Subtract in local wall time: a study-day boundary stays at the chosen hour through DST.
    fun day(timestampMs: Long): LocalDate = Instant.ofEpochMilli(timestampMs).atZone(zone)
        .toLocalDateTime().minusHours(snapshot.rolloverHour.toLong()).toLocalDate()
    fun events(start: LocalDate, end: LocalDate, deckId: Long? = null): List<Review> {
        require(!end.isBefore(start))
        return snapshot.reviews.distinctBy { it.id }.filter {
            it.ease in 1..4 && it.type in 0..2 && day(it.id) in start..end &&
                (deckId == null || cardMap[it.cardId]?.deckId == deckId)
        }
    }
    fun daily(start: LocalDate, end: LocalDate, deckId: Long? = null): List<Daily> {
        val first = snapshot.reviews.filter { it.type == 0 && it.ease in 1..4 }
            .mapNotNull { r -> cardMap[r.cardId]?.let { it.noteId to r.id } }
            .groupBy({ it.first }, { it.second }).mapValues { (_, ids) -> ids.min() }
        val grouped = events(start, end, deckId).groupBy { day(it.id) }
        return generateSequence(start) { if (it < end) it.plusDays(1) else null }.map { d ->
            val rows = grouped[d].orEmpty()
            val notes = rows.mapNotNull { cardMap[it.cardId]?.noteId }.distinct()
            Daily(d, rows.size, rows.map { it.cardId }.distinct().size,
                notes.count { first[it]?.let(::day) == d }, rows.sumOf { it.timeMs },
                rows.takeIf { it.isNotEmpty() }?.map { it.timeMs }?.average())
        }.toList()
    }
    fun retention(start: LocalDate, end: LocalDate, deckId: Long? = null): Retention {
        val rows = events(start, end, deckId).filter { it.type == 1 }
        val young = rows.filter { it.lastInterval < 21 }
        val mature = rows.filter { it.lastInterval >= 21 }
        return Retention(rows.size, rows.count { it.ease >= 2 }, young.size, young.count { it.ease >= 2 },
            mature.size, mature.count { it.ease >= 2 })
    }
    fun difficult(start: LocalDate, end: LocalDate, deckId: Long? = null, sort: WordSort = WordSort.AGAIN): List<Difficult> {
        val notes = snapshot.notes.associateBy { it.id }
        val rows = events(start, end, deckId).groupBy { cardMap[it.cardId]?.noteId }
            .mapNotNull { (nid, rs) -> nid?.let {
                Difficult(it, notes[it]?.fields?.firstOrNull().orEmpty(), rs.map { r -> r.cardId }.distinct(),
                    rs.count { r -> r.ease == 1 }, rs.filter { r -> r.ease == 1 }.maxOfOrNull { r -> r.id },
                    rs.map { r -> r.timeMs }.average(), rs.size)
            } }.filter { it.again > 0 }
        return when (sort) {
            WordSort.AGAIN -> rows.sortedByDescending { it.again }
            WordSort.RECENT -> rows.sortedByDescending { it.lastAgain }
            WordSort.TIME -> rows.sortedByDescending { it.averageMs }
            WordSort.REVIEWS -> rows.sortedByDescending { it.total }
        }
    }
    fun streak(today: LocalDate): Int {
        val days = snapshot.reviews.filter { it.ease in 1..4 && it.type in 0..2 }.map { day(it.id) }.toSet()
        var d = if (today in days) today else today.minusDays(1)
        var count = 0
        while (d in days) { count++; d = d.minusDays(1) }
        return count
    }
    // Snapshot estimate only. No FSRS simulation and no new-card order interpreted as a date.
    fun workload(nowMs: Long): Map<String, Int>? {
        val created = snapshot.creationSeconds ?: return null
        val today = day(nowMs)
        val createdDay = Instant.ofEpochSecond(created).atZone(zone).toLocalDate()
        val schedulerDay = java.time.temporal.ChronoUnit.DAYS.between(createdDay, today)
        val active = snapshot.cards.filter { it.originalDeckId == 0L && it.queue in listOf(1, 2, 3) }
        fun due(c: Card): Boolean = c.due?.let { if (c.queue == 1) it <= nowMs / 1000 else it <= schedulerDay } ?: false
        return mapOf("due" to active.count(::due), "overdue" to active.count {
            it.queue in listOf(2, 3) && (it.due ?: Long.MAX_VALUE) < schedulerDay
        }, "next7Days" to active.count { it.queue in listOf(2, 3) &&
            (it.due ?: Long.MAX_VALUE) > schedulerDay && (it.due ?: Long.MAX_VALUE) <= schedulerDay + 7 })
    }
}
