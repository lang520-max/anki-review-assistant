package org.ankireview.assistant

import android.content.Context
import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.os.CancellationSignal
import org.ankireview.core.*
import java.time.ZoneId

/** Only this class accesses Anki's ContentResolver; intentionally exposes no write methods. */
class AnkiReader(private val context: Context) {
    companion object {
        const val PERMISSION = "com.ichi2.anki.permission.READ_WRITE_DATABASE"
        const val AUTHORITY = "com.ichi2.anki.flashcards"
    }
    fun installed(): Boolean = context.packageManager.resolveContentProvider(AUTHORITY, 0) != null
    fun granted(): Boolean = context.checkSelfPermission(PERMISSION) == PackageManager.PERMISSION_GRANTED
    private fun query(path: String, columns: List<String>?, signal: CancellationSignal): Cursor =
        context.contentResolver.query(Uri.parse("content://$AUTHORITY/$path"), columns?.toTypedArray(),
            null, null, null, signal) ?: error("AnkiDroid 未返回数据，请先打开并完成初始化")
    fun read(collectionId: String, signal: CancellationSignal): Snapshot {
        check(installed()) { "AnkiDroid 未安装，或官方 Provider 不可用" }
        check(granted()) { "等待用户授予 AnkiDroid 数据权限" }
        val warnings = mutableListOf("官方 API 不提供 revlog；历史分析需要导入含学习记录的导出文件。",
            "当前状态是读取期间的快照，不保证跨多个查询的原子一致性。")
        val decks = query("decks", listOf("deck_id", "deck_name"), signal).use { c ->
            buildList { while (c.moveToNext()) { signal.throwIfCanceled(); add(Deck(c.long("deck_id")!!, c.string("deck_name").orEmpty())) } }
        }
        val notes = query("notes", listOf("_id", "flds"), signal).use { c ->
            buildList {
                while (c.moveToNext()) {
                    signal.throwIfCanceled(); check(size < 100_000) { "集合超过 10 万笔记，请分牌组导出后导入" }
                    add(Note(c.long("_id")!!, c.string("flds").orEmpty().split('\u001f')))
                }
            }
        }
        val base = listOf("_id", "note_id", "deck_id")
        val optional = listOf("queue", "type", "due", "interval", "reps", "lapses", "sm2_factor",
            "original_deck_id", "fsrs_difficulty", "fsrs_stability")
        val cards = try {
            val supported = optional.filter { field ->
                try { query("cards", listOf("_id", field), signal).use { }; true }
                catch (_: IllegalArgumentException) { warnings += "当前 AnkiDroid 不支持字段：$field"; false }
            }
            query("cards", base + supported, signal).use { c -> buildList {
                while (c.moveToNext()) {
                    signal.throwIfCanceled(); check(size < 200_000) { "集合超过 20 万卡片，请分牌组导入" }
                    val nid = c.long("note_id") ?: continue // Card deleted while lazy cursor was open.
                    add(Card(c.long("_id")!!, nid, c.long("deck_id") ?: continue,
                        c.int("queue"), c.int("type"), c.long("due"), c.int("interval"), c.int("reps"),
                        c.int("lapses"), c.int("sm2_factor"), c.long("original_deck_id") ?: 0,
                        c.double("fsrs_difficulty"), c.double("fsrs_stability")))
                }
            } }
        } catch (_: IllegalArgumentException) {
            warnings += "当前版本没有 /cards 接口；已读取牌组和笔记，卡片状态需要新版 AnkiDroid 或导出文件。"
            emptyList()
        }
        return Snapshot(collectionId = collectionId, source = "ankidroid-provider", capturedAt = System.currentTimeMillis(),
            zoneId = ZoneId.systemDefault().id, decks = decks, notes = notes, cards = cards, warnings = warnings)
    }
}

internal fun Cursor.long(name: String): Long? = getColumnIndex(name).takeIf { it >= 0 && !isNull(it) }?.let(::getLong)
internal fun Cursor.int(name: String): Int? = long(name)?.toInt()
internal fun Cursor.string(name: String): String? = getColumnIndex(name).takeIf { it >= 0 && !isNull(it) }?.let(::getString)
internal fun Cursor.double(name: String): Double? = getColumnIndex(name).takeIf { it >= 0 && !isNull(it) }?.let(::getDouble)
