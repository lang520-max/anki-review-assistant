package org.ankireview.assistant

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.ankireview.core.*
import java.time.*
import java.time.format.DateTimeFormatter

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme(colorScheme = lightColorScheme(primary = Color(0xFF176B61))) { AssistantApp() } }
        intent.data?.let(::handleLogin)
    }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); intent.data?.let(::handleLogin) }
    private fun handleLogin(uri: Uri) { lifecycleScope.launch {
        val ok = runCatching { withContext(Dispatchers.IO) { CloudCredentials(this@MainActivity).finishLogin(uri) } }.isSuccess
        android.widget.Toast.makeText(this@MainActivity, if (ok) "云端登录成功，仍需主动开启上传" else "授权失败或已过期，请重新登录", android.widget.Toast.LENGTH_LONG).show()
    } }
}

private data class Analysis(val daily: List<Daily>, val retention: Retention, val difficult: List<Difficult>,
                            val workload: Map<String, Int>?, val streak: Int)

@Composable fun AssistantApp(vm: AssistantViewModel = viewModel()) {
    val context = LocalContext.current
    val datasets by vm.datasets.collectAsStateWithLifecycle()
    val selected by vm.selected.collectAsStateWithLifecycle()
    val message by vm.message.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var includeContent by rememberSaveable { mutableStateOf(false) }
    var replaceHistory by rememberSaveable { mutableStateOf(false) }
    var deckId by rememberSaveable { mutableStateOf<Long?>(null) }
    var sorting by rememberSaveable { mutableStateOf(WordSort.AGAIN) }
    var zoneText by rememberSaveable { mutableStateOf(vm.zone()) }
    var hourText by rememberSaveable { mutableStateOf(vm.rollover().toString()) }
    var settingsError by remember { mutableStateOf<String?>(null) }
    var refresh by remember { mutableIntStateOf(0) }
    val reader = remember { AnkiReader(context) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        refresh++; vm.message.value = if (it) "已获得权限，可手动读取数据" else "等待用户授权；可在系统应用权限中重新开启"
    }
    val current = datasets.firstOrNull { it.id == selected } ?: datasets.firstOrNull()
    val snapshot by produceState<Snapshot?>(null, current, refresh) {
        value = withContext(Dispatchers.Default) {
            current?.let { dataJson.decodeFromString<Snapshot>(it.payload).copy(zoneId = vm.zone(), rolloverHour = vm.rollover()) }
        }
    }
    val import = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { vm.import(it, if (replaceHistory && snapshot?.source == "anki-export") snapshot?.collectionId else null) }
    }
    val export = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) snapshot?.let { vm.export(uri, it, includeContent) }
    }
    val today = remember(snapshot) { LocalDate.now(ZoneId.of(vm.zone())).let {
        Instant.now().atZone(ZoneId.of(vm.zone())).toLocalDateTime().minusHours(vm.rollover().toLong()).toLocalDate()
    } }
    var startText by rememberSaveable { mutableStateOf(today.minusDays(6).toString()) }
    var endText by rememberSaveable { mutableStateOf(today.toString()) }
    val start = runCatching { LocalDate.parse(startText) }.getOrNull()
    val end = runCatching { LocalDate.parse(endText) }.getOrNull()
    val rangeValid = start != null && end != null && !end.isBefore(start) &&
        java.time.temporal.ChronoUnit.DAYS.between(start, end) <= 3660
    val analysis by produceState<Analysis?>(null, snapshot, startText, endText, deckId, sorting) {
        value = null
        if (rangeValid) snapshot?.let { s -> value = withContext(Dispatchers.Default) {
            val stats = Statistics(s)
            Analysis(stats.daily(start!!, end!!, deckId), stats.retention(start, end, deckId),
                stats.difficult(start, end, deckId, sorting), stats.workload(System.currentTimeMillis()), stats.streak(today))
        } }
    }
    var confirmDelete by remember { mutableStateOf(false) }
    if (confirmDelete) AlertDialog(onDismissRequest = { confirmDelete = false },
        title = { Text("删除当前本地副本？") }, text = { Text("只删除助手缓存，不修改 AnkiDroid。") },
        confirmButton = { TextButton(onClick = { snapshot?.let { vm.delete(it.collectionId) }; confirmDelete = false }) { Text("删除") } },
        dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("取消") } })

    Scaffold(bottomBar = {
        NavigationBar {
            listOf("首页", "统计", "遗忘", "同步", "设置").forEachIndexed { i, title ->
                NavigationBarItem(selected = tab == i, onClick = { tab = i }, icon = { Text(listOf("⌂", "▥", "词", "↻", "⚙")[i]) }, label = { Text(title) })
            }
        }
    }) { padding ->
        Column(Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Anki Review Assistant", style = MaterialTheme.typography.headlineSmall)
            Text("只读 · 本地优先", color = MaterialTheme.colorScheme.primary)
            if (busy) { LinearProgressIndicator(Modifier.fillMaxWidth()); TextButton(onClick = vm::cancel) { Text("取消当前操作") } }
            Text(message, style = MaterialTheme.typography.bodyMedium)
            if (datasets.isNotEmpty()) {
                Text("数据来源（分别保存，不自动合并）：")
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    datasets.forEach { item -> FilterChip(selected = current?.id == item.id,
                        onClick = { vm.selected.value = item.id; deckId = null }, label = { Text(item.label) }) }
                }
            }
            val s = snapshot
            when (tab) {
                0 -> {
                    val status = when {
                        !reader.installed() -> "AnkiDroid 未安装或官方接口不可用"
                        !reader.granted() -> "等待用户授权"
                        s?.source == "ankidroid-provider" -> "数据读取成功（缓存）"
                        else -> "已获得权限"
                    }
                    InfoCard("连接状态", status)
                    if (!reader.installed()) TextButton(onClick = {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://ankidroid.org")))
                    }) { Text("获取 AnkiDroid") }
                    else if (!reader.granted()) Button(onClick = { permission.launch(AnkiReader.PERMISSION) }) { Text("授权读取 AnkiDroid") }
                    else Button(onClick = vm::readProvider, enabled = !busy) { Text("读取当前 AnkiDroid 数据") }
                    if (s != null) {
                        Text("最近数据读取：${formatTime(s.capturedAt, s.zoneId)}")
                        InfoCard("当前快照", "${s.decks.size} 个牌组 · ${s.notes.size} 条笔记 · ${s.cards.size} 张卡片")
                        val daily by produceState<Daily?>(null, s, today) {
                            value = withContext(Dispatchers.Default) { Statistics(s).daily(today, today).first() }
                        }
                        InfoCard("今日复习次数", if (s.historyAvailable) daily?.reviews?.toString() ?: "计算中" else "需要导入复习历史")
                        InfoCard("今日学习时间", if (s.historyAvailable) daily?.let { "${"%.1f".format(it.timeMs / 60000.0)} 分钟" } ?: "计算中" else "需要导入复习历史")
                        InfoCard("今日首次观察到学习的笔记", if (s.historyAvailable) daily?.newNotesObserved?.toString() ?: "计算中" else "需要导入复习历史")
                        InfoCard("待复习数量（快照估计）", analysis?.workload?.get("due")?.toString() ?: "缺少集合日界线信息，无法精确计算")
                        if (s.historyAvailable) Text("连续学习 ${analysis?.streak ?: 0} 天；历史快照可能缺少今天的数据。")
                        s.warnings.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                        s.decks.forEach { Text("${it.name}  ·  ID ${it.id}") }
                    }
                }
                1, 2 -> {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(7, 30, 90).forEach { days -> OutlinedButton(onClick = {
                            startText = today.minusDays(days - 1L).toString(); endText = today.toString()
                        }) { Text("$days 天") } }
                    }
                    OutlinedTextField(startText, { startText = it }, label = { Text("开始日期 YYYY-MM-DD") }, singleLine = true)
                    OutlinedTextField(endText, { endText = it }, label = { Text("结束日期 YYYY-MM-DD") }, singleLine = true)
                    if (!rangeValid) Text("请输入有效日期，开始不晚于结束，范围最多 3660 天", color = MaterialTheme.colorScheme.error)
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(deckId == null, { deckId = null }, label = { Text("全部牌组") })
                        s?.decks?.forEach { d -> FilterChip(deckId == d.id, { deckId = d.id }, label = { Text(d.name) }) }
                    }
                    if (s?.historyAvailable != true) Text("请先在同步页导入含学习记录的 Anki 导出文件。")
                    else analysis?.let { a ->
                        if (tab == 1) {
                            InfoCard("选定范围", "${a.daily.sumOf { it.reviews }} 次复习 · ${"%.1f".format(a.daily.sumOf { it.timeMs } / 60000.0)} 分钟")
                            Text("每日复习次数趋势")
                            TrendChart(a.daily)
                            val r = a.retention
                            InfoCard("观测复习成功率", r.rate?.let { "${"%.1f".format(it * 100)}%（${r.passed}/${r.reviewed}）" } ?: "没有常规复习事件")
                            Text("常规复习中 Hard / Good / Easy 均算成功；学习与重新学习单列，不等同于 FSRS 预测保持率。")
                            Text("年轻 ${r.youngPassed}/${r.youngTotal} · 成熟 ${r.maturePassed}/${r.matureTotal}（复习前间隔 ≥21 天）")
                            a.workload?.let { Text("快照估计：积压 ${it["overdue"]} 张，未来 7 天已排定 ${it["next7Days"]} 张。") }
                            a.daily.takeLast(90).forEach { d -> Text("${d.day}  ${d.reviews} 次 / ${d.distinctCards} 张 / ${"%.1f".format(d.timeMs / 60000.0)} 分钟") }
                        } else {
                            Row(Modifier.horizontalScroll(rememberScrollState())) {
                                WordSort.entries.forEach { sort -> FilterChip(sort == sorting, { sorting = sort },
                                    label = { Text(mapOf(WordSort.AGAIN to "Again 次数", WordSort.RECENT to "最近遗忘", WordSort.TIME to "平均耗时", WordSort.REVIEWS to "历史次数").getValue(sort)) }) }
                            }
                            Text("按笔记聚合，保留卡片关系；Again 包括学习、复习和重新学习阶段。")
                            if (a.difficult.isEmpty()) Text("选定范围没有 Again 事件。")
                            a.difficult.take(100).forEach { w ->
                                InfoCard(android.text.Html.fromHtml(w.word, android.text.Html.FROM_HTML_MODE_LEGACY).toString().ifBlank { "笔记 ${w.noteId}" },
                                    "Again ${w.again} · ${w.total} 次 · 平均 ${"%.1f".format(w.averageMs / 1000)} 秒\n卡片 ${w.cardIds.joinToString()}\n最近 Again ${w.lastAgain?.let { formatTime(it, s.zoneId) }}")
                            }
                        }
                    }
                }
                3 -> {
                    Text("官方 API 不提供 revlog。请在 AnkiDroid 中导出含学习进度／历史的集合或牌组，再选择文件。")
                    if (s?.source == "anki-export") Row {
                        Checkbox(replaceHistory, { replaceHistory = it }); Text("重新导入当前集合（完整替换；请确认来源相同）")
                    }
                    Button(onClick = { import.launch(arrayOf("*/*")) }, enabled = !busy) { Text("导入 .apkg / .colpkg 历史文件") }
                    Text("默认新建独立数据集；不会把不同集合的同号卡片混在一起。")
                    Row { Checkbox(includeContent, { includeContent = it }); Text("JSON 导出包含笔记正文（默认关闭）") }
                    Button(onClick = { export.launch("anki-review-${LocalDate.now()}.json") }, enabled = s != null && !busy) { Text("导出当前数据为 JSON") }
                    CloudSettings(vm, s)
                }
                4 -> {
                    Text("权限：底层 AnkiDroid 可能授予读写合并权限，本应用只调用查询接口。")
                    OutlinedButton(onClick = { context.startActivity(Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:${context.packageName}"))) }) { Text("系统权限与撤销授权") }
                    OutlinedTextField(zoneText, { zoneText = it }, label = { Text("统计时区，例如 Asia/Shanghai") })
                    OutlinedTextField(hourText, { hourText = it }, label = { Text("学习日开始小时 0—23（默认 4）") })
                    Button(onClick = {
                        try { vm.saveDaySettings(zoneText, hourText.toInt()); settingsError = null; refresh++ }
                        catch (_: Exception) { settingsError = "请输入有效 IANA 时区和 0—23 的小时" }
                    }) { Text("保存统计设置") }
                    settingsError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    Text("本地数据库保存在应用私有目录，关闭 Android 自动备份。卸载会删除本地副本。JSON 导出文件由你自行保管。")
                    Text("学习耗时来自 Anki 记录值，可能受计时上限影响；首次观察到学习不保证是真正首次学习。")
                    OutlinedButton(onClick = { confirmDelete = true }, enabled = s != null && !busy) { Text("删除当前本地副本") }
                    Text("版本 0.1.0 · Apache-2.0 · 不添加、不修改、不删除 Anki 卡片")
                }
            }
        }
    }
}

@Composable private fun InfoCard(title: String, value: String) {
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium); Text(value)
    } }
}
@Composable private fun TrendChart(rows: List<Daily>) {
    Canvas(Modifier.fillMaxWidth().height(120.dp)) {
        val max = rows.maxOfOrNull { it.reviews }?.coerceAtLeast(1) ?: 1
        val width = size.width / rows.size.coerceAtLeast(1)
        rows.forEachIndexed { i, d ->
            drawLine(Color(0xFF176B61), Offset((i + .5f) * width, size.height),
                Offset((i + .5f) * width, size.height * (1 - d.reviews.toFloat() / max)), strokeWidth = (width * .7f).coerceAtLeast(1f))
        }
    }
}
private fun formatTime(ms: Long, zone: String) = Instant.ofEpochMilli(ms).atZone(ZoneId.of(zone))
    .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))
