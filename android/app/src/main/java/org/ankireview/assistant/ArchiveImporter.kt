package org.ankireview.assistant

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.net.Uri
import android.os.CancellationSignal
import com.github.luben.zstd.ZstdInputStream
import org.ankireview.core.*
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.time.ZoneId
import java.util.zip.ZipFile

/** Operates exclusively on a private temporary copy; never opens Anki's live database. */
class ArchiveImporter(private val context: Context) {
    private val limit = 512L * 1024 * 1024
    private fun copyBounded(input: InputStream, out: OutputStream, signal: CancellationSignal) {
        val buffer = ByteArray(64 * 1024); var count = 0L
        while (true) {
            signal.throwIfCanceled(); val n = input.read(buffer); if (n < 0) break
            count += n; require(count <= limit) { "文件或解压后数据库超过 512 MB" }; out.write(buffer, 0, n)
        }
    }
    fun read(uri: Uri, collectionId: String, zoneId: String, rollover: Int, signal: CancellationSignal): Snapshot {
        val directory = File(context.cacheDir, "import-${java.util.UUID.randomUUID()}").apply { mkdirs() }
        try {
            val archive = File(directory, "archive.zip")
            context.contentResolver.openInputStream(uri).use { input ->
                requireNotNull(input) { "无法打开文件" }; archive.outputStream().use { copyBounded(input, it, signal) }
            }
            val database = File(directory, "collection.sqlite")
            ZipFile(archive).use { zip ->
                val entries = zip.entries(); var entryCount = 0
                while (entries.hasMoreElements()) {
                    signal.throwIfCanceled(); val name = entries.nextElement().name
                    require(++entryCount <= 100_000) { "导出包条目过多" }
                    require(!name.startsWith('/') && '\\' !in name && ".." !in name.split('/')) { "导出包包含不安全路径" }
                }
                // Select newer formats first; old compatibility entries may only be placeholders.
                val entry = listOf("collection.anki21b", "collection.anki21", "collection.anki2")
                    .firstNotNullOfOrNull { zip.getEntry(it) } ?: error("不是支持的 Anki 导出文件")
                require(!entry.isDirectory && entry.size <= limit) { "无效或过大的数据库" }
                zip.getInputStream(entry).use { raw ->
                    val input = if (entry.name.endsWith("21b")) ZstdInputStream(raw) else raw
                    input.use { stream -> database.outputStream().use { copyBounded(stream, it, signal) } }
                }
            }
            return parse(database, collectionId, zoneId, rollover, signal)
        } finally { directory.deleteRecursively() }
    }
    internal fun parse(file: File, collectionId: String, zoneId: String, rollover: Int, signal: CancellationSignal): Snapshot {
        SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READONLY).use { db ->
            val warnings = mutableListOf("导入文件是历史快照，不会自动跟随 AnkiDroid 更新。",
                "导出历史可能不完整；新增词按首次观察到的学习事件统计。",
                "到期与未来负担按所选时区、学习日边界估算，排除筛选牌组；不包含未来新增词。")
            var creation: Long? = null
            val decks = mutableListOf<Deck>()
            db.rawQuery("SELECT crt, ver, decks FROM col", null).use { c ->
                require(c.moveToFirst()) { "缺少集合元信息" }
                require(c.getInt(1) in listOf(11, 16, 17, 18)) { "不支持的集合数据库版本：${c.getInt(1)}" }
                creation = c.getLong(0)
                val old = JSONObject(c.getString(2).ifBlank { "{}" })
                old.keys().forEach { key -> decks += Deck(key.toLong(), old.getJSONObject(key).optString("name", key)) }
            }
            if (decks.isEmpty()) {
                db.rawQuery("SELECT id, name FROM decks", null).use { c ->
                    while (c.moveToNext()) decks += Deck(c.getLong(0), c.getString(1).replace('\u001f', ':'))
                }
            }
            val notes = db.rawQuery("SELECT id, flds FROM notes", null).use { c -> buildList {
                while (c.moveToNext()) {
                    signal.throwIfCanceled(); require(size < 100_000) { "最多支持 10 万笔记" }
                    add(Note(c.getLong(0), c.getString(1).split('\u001f')))
                }
            } }
            val cards = db.rawQuery("SELECT id,nid,did,queue,type,due,ivl,reps,lapses,factor,odid FROM cards", null).use { c -> buildList {
                while (c.moveToNext()) {
                    signal.throwIfCanceled(); require(size < 200_000) { "最多支持 20 万卡片" }
                    add(Card(c.getLong(0),c.getLong(1),c.getLong(2),c.getInt(3),c.getInt(4),c.getLong(5),
                        c.getInt(6),c.getInt(7),c.getInt(8),c.getInt(9),c.getLong(10)))
                }
            } }
            val reviews = db.rawQuery("SELECT id,cid,ease,ivl,lastIvl,time,type FROM revlog ORDER BY id", null).use { c -> buildList {
                while (c.moveToNext()) {
                    signal.throwIfCanceled(); require(size < 1_000_000) { "最多支持 100 万复习事件" }
                    add(Review(c.getLong(0),c.getLong(1),c.getInt(2),c.getInt(3),c.getInt(4),c.getLong(5).coerceAtLeast(0),c.getInt(6)))
                }
            } }
            return Snapshot(collectionId = collectionId, source = "anki-export", capturedAt = System.currentTimeMillis(),
                zoneId = ZoneId.of(zoneId).id, rolloverHour = rollover, creationSeconds = creation, historyAvailable = true,
                decks = decks, notes = notes, cards = cards, reviews = reviews, warnings = warnings)
        }
    }
}
