package org.ankireview.assistant

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import org.ankireview.core.Note
import org.ankireview.core.Snapshot
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.UUID

class LargeSnapshotStorageTest {
    @Test fun payloadLargerThanCursorWindowIsStoredOutsideRoom() = runBlocking {
        val context=ApplicationProvider.getApplicationContext<Context>()
        val dao=AppDatabase.get(context).snapshots()
        val id=UUID.randomUUID().toString()
        val text="x".repeat(3*1024*1024)
        val snapshot=Snapshot(collectionId=id,source="synthetic",capturedAt=0,zoneId="UTC",notes=listOf(Note(1,listOf(text))))
        var filename: String?=null
        try {
            dao.save(snapshot,"synthetic large snapshot",context)
            val stored=dao.get(id)!!; filename=stored.payload
            assertTrue(stored.payload.length<200)
            assertEquals(text.length,stored.decode(context).notes.first().fields.first().length)
        } finally {
            dao.delete(id); filename?.let { File(context.filesDir,"collections/$it").delete() }
        }
    }
}
