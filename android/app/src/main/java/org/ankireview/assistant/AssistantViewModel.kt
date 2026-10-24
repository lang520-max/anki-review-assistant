package org.ankireview.assistant

import android.app.Application
import android.net.Uri
import android.os.CancellationSignal
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.encodeToString
import org.ankireview.core.*
import java.time.ZoneId
import java.util.UUID

class AssistantViewModel(app: Application) : AndroidViewModel(app) {
    val dao = AppDatabase.get(app).snapshots()
    val datasets = dao.watch().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val selected = MutableStateFlow<String?>(null)
    val message = MutableStateFlow("等待连接 AnkiDroid，或导入含学习记录的文件")
    val busy = MutableStateFlow(false)
    private var signal: CancellationSignal? = null
    private var task: Job? = null
    val prefs = app.getSharedPreferences("settings", 0)
    val providerId: String = prefs.getString("provider_id", null) ?: UUID.randomUUID().toString().also {
        prefs.edit().putString("provider_id", it).apply()
    }
    fun runTask(block: suspend (CancellationSignal) -> Unit) {
        if (busy.value) return
        busy.value = true
        val cancellation = CancellationSignal().also { signal = it }
        task = viewModelScope.launch {
            try { withContext(Dispatchers.IO) { block(cancellation) } }
            catch (_: CancellationException) { message.value = "操作已取消，上次成功数据仍保留" }
            catch (_: android.os.OperationCanceledException) { message.value = "操作已取消，上次成功数据仍保留" }
            catch (_: SecurityException) { message.value = "授权失效，请重新授权或重新选择文件" }
            catch (e: Exception) {
                message.value = when (e) {
                    is IllegalArgumentException, is IllegalStateException -> "操作失败：${e.message?.take(180)}"
                    else -> "读取或导出失败（${e.javaClass.simpleName}），请检查文件格式和 AnkiDroid 初始化状态"
                }
            } finally { busy.value = false; signal = null }
        }
    }
    fun readProvider() = runTask { cancellation ->
        val snapshot = AnkiReader(getApplication()).read(providerId, cancellation)
            .copy(zoneId = zone(), rolloverHour = rollover())
        dao.save(snapshot, "AnkiDroid 当前状态", getApplication()); selected.value = providerId; message.value = "数据读取成功"
    }
    fun import(uri: Uri, replaceId: String?) = runTask { cancellation ->
        val id = replaceId ?: UUID.randomUUID().toString()
        val snapshot = ArchiveImporter(getApplication()).read(uri, id, zone(), rollover(), cancellation)
        val old = replaceId?.let { dao.get(it) }
        dao.save(snapshot, old?.label ?: "历史导入 ${java.time.LocalDate.now()}", getApplication())
        selected.value = id; message.value = "导入成功：${snapshot.reviews.size} 条历史。相同集合重新导入会完整替换，避免重复和保留已撤销事件。"
    }
    fun export(uri: Uri, snapshot: Snapshot, content: Boolean) = runTask { _ ->
        val value = if (content) snapshot else snapshot.copy(notes = snapshot.notes.map { it.copy(fields = emptyList()) })
        requireNotNull(getApplication<Application>().contentResolver.openOutputStream(uri, "wt")).bufferedWriter().use {
            it.write(dataJson.encodeToString(value))
        }
        message.value = "JSON 已导出；文件包含私人学习记录，请自行保管"
    }
    fun zone() = prefs.getString("zone", ZoneId.systemDefault().id)!!
    fun rollover() = prefs.getInt("rollover", 4)
    fun saveDaySettings(zone: String, hour: Int) {
        ZoneId.of(zone); require(hour in 0..23)
        prefs.edit().putString("zone", zone).putInt("rollover", hour).apply()
        message.value = "统计时区与学习日边界已保存"
    }
    fun cancel() { signal?.cancel(); task?.cancel() }
    fun delete(id: String) = runTask { _ ->
        val stored = dao.get(id); dao.delete(id)
        stored?.let { java.io.File(getApplication<Application>().filesDir,"collections/${it.payload}").delete() }
        java.io.File(getApplication<Application>().filesDir,"sync-checkpoints/$id.json").delete()
        androidx.work.WorkManager.getInstance(getApplication()).cancelUniqueWork("sync-$id")
        selected.value = null; message.value = "已删除助手中的本地副本，AnkiDroid 数据不受影响"
    }
    override fun onCleared() { cancel(); super.onCleared() }
}
