package org.ankireview.assistant

import android.content.Context
import androidx.room.*
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.encodeToString
import org.ankireview.core.*
import java.io.File
import java.util.UUID
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext

@Entity(tableName = "snapshots")
data class StoredSnapshot(@PrimaryKey val id: String, val label: String, val payload: String, val updatedAt: Long)
@Dao interface SnapshotDao {
    @Query("SELECT * FROM snapshots ORDER BY updatedAt DESC") fun watch(): Flow<List<StoredSnapshot>>
    @Query("SELECT * FROM snapshots WHERE id = :id") suspend fun get(id: String): StoredSnapshot?
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(value: StoredSnapshot)
    @Query("DELETE FROM snapshots WHERE id = :id") suspend fun delete(id: String)
    @Query("DELETE FROM snapshots") suspend fun clear()
}
@Database(entities = [StoredSnapshot::class], version = 1, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun snapshots(): SnapshotDao
    companion object {
        @Volatile private var instance: AppDatabase? = null
        fun get(context: Context): AppDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(context.applicationContext, AppDatabase::class.java, "assistant.db")
                .build().also { instance = it }
        }
    }
}
fun StoredSnapshot.decode(context: Context): Snapshot = dataJson.decodeFromString(
    File(context.filesDir,"collections/$payload").readText())

// Keep large payloads out of SQLite CursorWindow (commonly ~2 MiB per window).
// Publish the immutable file before the metadata transaction; retain old data on failure.
suspend fun SnapshotDao.save(snapshot: Snapshot, label: String, context: Context) = withContext(NonCancellable) {
    val directory = File(context.filesDir,"collections").apply { mkdirs() }
    val previous = get(snapshot.collectionId)
    val file = File(directory,"${snapshot.collectionId}-${UUID.randomUUID()}.json")
    try {
        file.writeText(dataJson.encodeToString(snapshot))
        put(StoredSnapshot(snapshot.collectionId,label,file.name,snapshot.capturedAt))
    } catch (e: Exception) { file.delete(); throw e }
    previous?.let { File(directory,it.payload).delete() }
}
