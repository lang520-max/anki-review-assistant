package org.ankireview.core

import java.time.Instant
import java.time.LocalDate
import kotlin.test.*

class StatisticsTest {
    private fun ms(t: String) = Instant.parse(t).toEpochMilli()
    private fun snapshot(rows: List<Review>) = Snapshot(collectionId = "test", source = "fixture", capturedAt = 0,
        zoneId = "UTC", historyAvailable = true, notes = listOf(Note(10, listOf("word"))),
        cards = listOf(Card(1,10,100), Card(2,10,100)), reviews = rows)
    @Test fun `four am cutoff and DST are local wall time`() {
        val stats = Statistics(snapshot(emptyList()).copy(zoneId = "America/New_York"))
        assertEquals(LocalDate.parse("2026-03-07"), stats.day(ms("2026-03-08T07:30:00Z")))
        assertEquals(LocalDate.parse("2026-03-08"), stats.day(ms("2026-03-08T08:00:00Z")))
    }
    @Test fun `hard counts as success and learning does not affect retention`() {
        val t = ms("2026-01-01T12:00:00Z")
        val stats = Statistics(snapshot(listOf(Review(t,1,2,30,21,1200,1),
            Review(t+1,2,1,1,1,800,0), Review(t+2,1,1,1,30,1000,1), Review(t+3,1,4,1,30,100,4))))
        val d = LocalDate.parse("2026-01-01")
        val r = stats.retention(d,d)
        assertEquals(2,r.reviewed); assertEquals(.5,r.rate)
        assertEquals(2,r.matureTotal); assertEquals(1,r.maturePassed)
    }
    @Test fun `duplicate events do not inflate counts and sibling cards share a note`() {
        val t = ms("2026-01-01T12:00:00Z")
        val a = Review(t,1,1,1,0,500,0)
        val stats = Statistics(snapshot(listOf(a,a,Review(t+1,2,1,1,0,1500,0))))
        val d = LocalDate.parse("2026-01-01")
        val day = stats.daily(d,d).first()
        assertEquals(2,day.reviews); assertEquals(1,day.newNotesObserved)
        assertEquals(1,stats.difficult(d,d).size)
        assertEquals(2,stats.difficult(d,d).first().again)
    }
    @Test fun `new card order is never a timestamp and missing metadata is unavailable`() {
        val s = snapshot(emptyList())
        assertNull(Statistics(s).workload(ms("2026-01-01T12:00:00Z")))
        assertEquals(0,Statistics(s.copy(creationSeconds=1700000000,
            cards=listOf(Card(1,10,100,queue=0,due=1)))).workload(ms("2026-01-01T12:00:00Z"))!!["due"])
    }
    @Test fun `empty denominator is unknown`() {
        val d = LocalDate.parse("2026-01-01")
        assertNull(Statistics(snapshot(emptyList())).retention(d,d).rate)
    }
}
