package org.ankireview.assistant

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.net.Uri
import android.os.CancellationSignal
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.github.luben.zstd.ZstdOutputStream
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

@RunWith(AndroidJUnit4::class)
class ArchiveImportTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private fun database(directory: File): File {
        val file = File(directory,"synthetic.sqlite")
        SQLiteDatabase.openOrCreateDatabase(file,null).use { db ->
            db.execSQL("CREATE TABLE col(crt INTEGER,ver INTEGER,decks TEXT)")
            db.execSQL("INSERT INTO col VALUES(1700000000,11,'{\"100\":{\"name\":\"Synthetic\"}}')")
            db.execSQL("CREATE TABLE notes(id INTEGER,flds TEXT)")
            db.execSQL("INSERT INTO notes VALUES(10,'synthetic word')")
            db.execSQL("CREATE TABLE cards(id INTEGER,nid INTEGER,did INTEGER,queue INTEGER,type INTEGER,due INTEGER,ivl INTEGER,reps INTEGER,lapses INTEGER,factor INTEGER,odid INTEGER)")
            db.execSQL("INSERT INTO cards VALUES(1,10,100,2,2,1000,30,2,1,2500,0)")
            db.execSQL("CREATE TABLE revlog(id INTEGER,cid INTEGER,ease INTEGER,ivl INTEGER,lastIvl INTEGER,time INTEGER,type INTEGER)")
            db.execSQL("INSERT INTO revlog VALUES(1767268800000,1,2,30,21,1200,1)")
        }
        return file
    }
    private fun archive(compressed: Boolean, malicious: Boolean = false) {
        val dir=File(context.cacheDir,"fixture-${java.util.UUID.randomUUID()}").apply { mkdirs() }
        try {
            val db=database(dir); val before=db.readBytes()
            val file=File(dir,"synthetic.apkg")
            ZipOutputStream(file.outputStream()).use { zip ->
                zip.putNextEntry(ZipEntry(if(compressed) "collection.anki21b" else "collection.anki2"))
                val bytes=if(compressed) java.io.ByteArrayOutputStream().also { out ->
                    ZstdOutputStream(out).use { it.write(before) }
                }.toByteArray() else before
                zip.write(bytes); zip.closeEntry()
                zip.putNextEntry(ZipEntry(if(malicious) "../../must-not-extract" else "media/unused"));zip.write(byteArrayOf(1));zip.closeEntry()
            }
            if (malicious) {
                val error=runCatching { ArchiveImporter(context).read(Uri.fromFile(file),"synthetic","UTC",4,CancellationSignal()) }.exceptionOrNull()
                assertTrue(error is java.util.zip.ZipException || error is IllegalArgumentException)
                assertArrayEquals(before,db.readBytes())
                assertFalse(File(context.cacheDir,"must-not-extract").exists())
                return
            }
            val result=ArchiveImporter(context).read(Uri.fromFile(file),"synthetic","UTC",4,CancellationSignal())
            assertEquals(1,result.reviews.size); assertEquals(2,result.reviews.first().ease)
            assertEquals(1,result.cards.size); assertEquals("Synthetic",result.decks.first().name)
            assertArrayEquals(before,db.readBytes())
            assertFalse(File(context.cacheDir,"must-not-extract").exists())
        } finally { dir.deleteRecursively() }
    }
    @Test fun importsLegacyWithoutChangingOriginal() = archive(false)
    @Test fun importsZstdCollectionAndIgnoresOtherEntries() = archive(true)
    @Test fun rejectsTraversalEntriesWithoutExtracting() = archive(false,true)
    @Test fun refusesUnknownSchema() {
        val dir=File(context.cacheDir,"unknown-${java.util.UUID.randomUUID()}").apply { mkdirs() }
        try {
            val db=database(dir)
            SQLiteDatabase.openDatabase(db.path,null,SQLiteDatabase.OPEN_READWRITE).use { it.execSQL("UPDATE col SET ver=999") }
            try {
                ArchiveImporter(context).parse(db,"synthetic","UTC",4,CancellationSignal())
                fail("Unknown schema must be rejected")
            } catch (_: IllegalArgumentException) { }
        } finally { dir.deleteRecursively() }
    }
}
