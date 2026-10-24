package org.ankireview.assistant

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.platform.LocalContext
import androidx.work.*
import kotlinx.serialization.encodeToString
import org.ankireview.core.*
import org.json.JSONObject
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.io.File
import java.util.Base64
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal fun https(value: String): String {
    val uri = java.net.URI(value)
    require(uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null && uri.fragment == null && uri.query == null) { "必须使用有效 HTTPS 地址" }
    return value.trimEnd('/')
}
private fun form(value: String) = URLEncoder.encode(value, "UTF-8")
private fun randomString(): String = ByteArray(32).also { SecureRandom().nextBytes(it) }.let {
    Base64.getUrlEncoder().withoutPadding().encodeToString(it)
}
class CloudCredentials(private val context: Context) {
    val prefs = context.getSharedPreferences("cloud", 0)
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (store.getKey("cloud-token", null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("cloud-token", KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun setSecret(name: String, value: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        prefs.edit().putString(name, Base64.getEncoder().encodeToString(cipher.iv + cipher.doFinal(value.toByteArray()))).commit()
    }
    fun secret(name: String): String? = prefs.getString(name, null)?.let {
        val bytes = Base64.getDecoder().decode(it)
        String(Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0,12))) }
            .doFinal(bytes.copyOfRange(12, bytes.size)))
    }
    fun disconnect() {
        prefs.edit().putBoolean("enabled", false).remove("access").remove("refresh").remove("state").remove("verifier").commit()
        WorkManager.getInstance(context).cancelAllWorkByTag("cloud-sync")
    }
    fun request(url: String, body: String? = null, token: String? = null, method: String = "GET", contentType: String = "application/json"): JSONObject {
        val connection = URL(https(url)).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15000; connection.readTimeout = 30000; connection.instanceFollowRedirects = false
            connection.requestMethod = method
            token?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
            connection.setRequestProperty("Accept", "application/json")
            if (body != null) {
                connection.doOutput = true; connection.setRequestProperty("Content-Type", contentType)
                connection.outputStream.use { it.write(body.toByteArray()) }
            }
            require(connection.responseCode in 200..299) { "服务器返回 HTTP ${connection.responseCode}" }
            return connection.inputStream.bufferedReader().use { JSONObject(it.readText()) }
        } finally { connection.disconnect() }
    }
    fun startLogin(server: String, issuer: String, clientId: String): Uri {
        disconnect()
        prefs.all.keys.filter { it.startsWith("hash:") || it.startsWith("revision:") || it.startsWith("synced:") }
            .forEach { prefs.edit().remove(it).commit() }
        File(context.filesDir,"sync-checkpoints").deleteRecursively()
        require(clientId.isNotBlank()) { "请输入 OAuth 公共客户端 ID" }
        val config = request(https(issuer) + "/.well-known/openid-configuration")
        require(config.getString("issuer").trimEnd('/') == https(issuer)) { "授权服务器 issuer 不匹配" }
        val state = randomString(); val verifier = randomString()
        val challenge = Base64.getUrlEncoder().withoutPadding().encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray()))
        prefs.edit().putString("server", https(server)).putString("issuer", https(issuer)).putString("client", clientId)
            .putString("state", state).putString("token_endpoint", https(config.getString("token_endpoint")))
            .putLong("login_started", System.currentTimeMillis()).commit()
        setSecret("verifier", verifier)
        return Uri.parse(https(config.getString("authorization_endpoint"))).buildUpon()
            .appendQueryParameter("client_id", clientId).appendQueryParameter("response_type", "code")
            .appendQueryParameter("redirect_uri", "org.ankireview.assistant://oauth/callback")
            .appendQueryParameter("scope", "openid offline_access study:read study:sync study:delete")
            .appendQueryParameter("state", state).appendQueryParameter("code_challenge", challenge)
            .appendQueryParameter("code_challenge_method", "S256").build()
    }
    fun finishLogin(uri: Uri) {
        require(uri.scheme == "org.ankireview.assistant" && uri.host == "oauth" && uri.path == "/callback")
        val expected = prefs.getString("state", null)
        require(expected != null && uri.getQueryParameter("state") == expected &&
            System.currentTimeMillis() - prefs.getLong("login_started", 0) < 600000) { "授权请求已过期或不匹配" }
        val code = requireNotNull(uri.getQueryParameter("code")) { "授权被取消" }
        val verifier = requireNotNull(secret("verifier"))
        prefs.edit().remove("state").remove("verifier").commit()
        val result = request(prefs.getString("token_endpoint", null)!!,
            "grant_type=authorization_code&client_id=${form(prefs.getString("client", "")!!)}&code=${form(code)}&code_verifier=${form(verifier)}&redirect_uri=${form("org.ankireview.assistant://oauth/callback")}",
            method = "POST", contentType = "application/x-www-form-urlencoded")
        saveTokens(result)
    }
    private fun saveTokens(result: JSONObject) {
        setSecret("access", result.getString("access_token"))
        result.optString("refresh_token").takeIf { it.isNotBlank() }?.let { setSecret("refresh", it) }
        prefs.edit().putLong("expires", System.currentTimeMillis() + result.getLong("expires_in") * 1000).commit()
    }
    @Synchronized fun accessToken(): String {
        if (prefs.getLong("expires", 0) < System.currentTimeMillis() + 60000) {
            val refresh = requireNotNull(secret("refresh")) { "请重新登录" }
            saveTokens(request(prefs.getString("token_endpoint", null)!!,
                "grant_type=refresh_token&client_id=${form(prefs.getString("client", "")!!)}&refresh_token=${form(refresh)}",
                method="POST", contentType="application/x-www-form-urlencoded"))
        }
        return requireNotNull(secret("access")) { "请先授权登录" }
    }
}

class CloudSyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
        val credentials = CloudCredentials(applicationContext)
        val id = inputData.getString("collection") ?: return@withContext Result.failure()
        if (!credentials.prefs.getBoolean("enabled", false)) return@withContext Result.failure()
        try {
            val record = AppDatabase.get(applicationContext).snapshots().get(id) ?: return@withContext Result.failure()
            val snapshot = record.decode(applicationContext)
            val allowed = credentials.prefs.getStringSet("decks", emptySet()).orEmpty().mapNotNull { it.toLongOrNull() }.toSet()
            require(allowed.isNotEmpty())
            val cards = snapshot.cards.filter { it.deckId in allowed }
            val noteIds = cards.map { it.noteId }.toSet(); val cardIds = cards.map { it.id }.toSet()
            val filtered = snapshot.copy(decks = snapshot.decks.filter { it.id in allowed }, cards = cards,
                notes = snapshot.notes.filter { it.id in noteIds }.map { if (credentials.prefs.getBoolean("content", false)) it else it.copy(fields=emptyList()) },
                reviews = snapshot.reviews.filter { it.cardId in cardIds })
            val json = dataJson.encodeToString(filtered)
            val hash = MessageDigest.getInstance("SHA-256").digest(json.toByteArray()).joinToString("") { "%02x".format(it) }
            if (hash == credentials.prefs.getString("hash:$id", null)) return@withContext Result.success()
            val checkpoint = File(File(applicationContext.filesDir,"sync-checkpoints").apply { mkdirs() }, "$id.json")
            // Reconcile revision before first upload after login; never reuse another account's checkpoint.
            val previous = if (checkpoint.exists()) JSONObject(checkpoint.readText()) else null
            val revision = if (previous != null) credentials.prefs.getLong("revision:$id", 0) else {
                val list = credentials.request(credentials.prefs.getString("server",null)!!+"/v1/collections",token=credentials.accessToken()).getJSONArray("collections")
                (0 until list.length()).map { list.getJSONObject(it) }.firstOrNull { it.getString("id")==id }?.getLong("revision") ?: 0
            }
            val next = JSONObject(json)
            val body = JSONObject().put("baseRevision", revision).put("batchId", hash)
            if (previous == null) body.put("snapshot",next) else {
                val metadata = JSONObject(json); val upserts = JSONObject(); val deletes = JSONObject()
                listOf("decks","notes","cards","reviews").forEach { table ->
                    fun indexed(value: JSONObject): Map<Long,JSONObject> {
                        val array = value.getJSONArray(table)
                        return (0 until array.length()).associate { i -> array.getJSONObject(i).let { it.getLong("id") to it } }
                    }
                    val before = indexed(previous); val after = indexed(next)
                    upserts.put(table,JSONArray(after.filter { (key,value) -> before[key]?.toString()!=value.toString() }.values.toList()))
                    deletes.put(table,JSONArray((before.keys-after.keys).toList()))
                    metadata.remove(table)
                }
                body.put("metadata",metadata).put("upserts",upserts).put("deletes",deletes)
            }
            if (isStopped || !credentials.prefs.getBoolean("enabled", false)) return@withContext Result.failure()
            val response = credentials.request(credentials.prefs.getString("server", null)!! + "/v1/collections/$id/sync",
                body.toString(), credentials.accessToken(), "POST")
            if (isStopped || !credentials.prefs.getBoolean("enabled", false)) return@withContext Result.failure()
            val temporary = File(checkpoint.path+".tmp").apply { writeText(json) }
            check(temporary.renameTo(checkpoint)) { "无法保存同步检查点" }
            credentials.prefs.edit().putString("hash:$id", hash).putLong("revision:$id", response.getLong("revision"))
                .putLong("synced:$id", System.currentTimeMillis()).putString("status", "同步成功").commit()
            Result.success()
        } catch (_: Exception) {
            credentials.prefs.edit().putString("status", "同步失败，检查网络或重新授权；HTTP 409 时需先核对远端版本").commit()
            if (runAttemptCount < 5) Result.retry() else Result.failure()
        }
    }
    companion object {
        fun enqueue(context: Context, id: String) {
            val request = OneTimeWorkRequestBuilder<CloudSyncWorker>()
                .setInputData(workDataOf("collection" to id)).addTag("cloud-sync")
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS).build()
            WorkManager.getInstance(context).enqueueUniqueWork("sync-$id", ExistingWorkPolicy.REPLACE, request)
        }
    }
}

@Composable fun CloudSettings(vm: AssistantViewModel, snapshot: Snapshot?) {
    val context = LocalContext.current
    val credentials = remember { CloudCredentials(context) }
    var server by rememberSaveable { mutableStateOf(credentials.prefs.getString("server", "")!!) }
    var issuer by rememberSaveable { mutableStateOf(credentials.prefs.getString("issuer", "")!!) }
    var client by rememberSaveable { mutableStateOf(credentials.prefs.getString("client", "anki-android")!!) }
    var enabled by remember { mutableStateOf(credentials.prefs.getBoolean("enabled", false)) }
    var content by remember { mutableStateOf(credentials.prefs.getBoolean("content", false)) }
    var decks by remember { mutableStateOf(credentials.prefs.getStringSet("decks", emptySet()).orEmpty().toSet()) }
    Text("私人云同步（默认关闭，需自行部署服务）")
    OutlinedTextField(server, { server=it }, label={Text("HTTPS 服务地址")})
    OutlinedTextField(issuer, { issuer=it }, label={Text("OIDC issuer 地址")})
    OutlinedTextField(client, { client=it }, label={Text("OAuth 公共客户端 ID")})
    Button(onClick={ vm.runTask { _ ->
        val uri = credentials.startLogin(server, issuer, client)
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) { context.startActivity(Intent(Intent.ACTION_VIEW,uri)) }
    } }) { Text("在浏览器授权登录") }
    Text("选择允许上传的牌组：")
    snapshot?.decks?.forEach { d -> Row {
        Checkbox(d.id.toString() in decks, { checked -> decks = if (checked) decks + d.id.toString() else decks - d.id.toString()
            credentials.prefs.edit().putStringSet("decks",decks).apply() }); Text(d.name)
    } }
    Row { Checkbox(content, { content=it; credentials.prefs.edit().putBoolean("content",it).apply() }); Text("允许上传笔记正文") }
    Row { Switch(enabled, { checked ->
        enabled=checked; credentials.prefs.edit().putBoolean("enabled",checked).commit()
        if (!checked) androidx.work.WorkManager.getInstance(context).cancelAllWorkByTag("cloud-sync")
    }); Text("明确授权上传所选牌组学习数据") }
    Button(onClick={ snapshot?.let { CloudSyncWorker.enqueue(context,it.collectionId); vm.message.value="同步任务已排队，恢复网络后执行" } },
        enabled=enabled && snapshot != null && decks.isNotEmpty()) { Text("同步所选牌组") }
    Text(credentials.prefs.getString("status","尚未同步")!!)
    OutlinedButton(onClick={ credentials.disconnect(); enabled=false; vm.message.value="本机授权已清除，上传任务已取消；可在授权服务器撤销其他会话" }) { Text("断开本机云同步授权") }
    var confirm by remember { mutableStateOf(false) }
    OutlinedButton(onClick={ confirm=true },enabled=snapshot!=null) { Text("删除当前集合的远程数据") }
    if(confirm) AlertDialog(onDismissRequest={confirm=false}, title={Text("删除远程数据？")}, text={Text("会先停止上传，再删除远程当前集合。本地与 AnkiDroid 保留。")},
        confirmButton={TextButton(onClick={ confirm=false; enabled=false
            credentials.prefs.edit().putBoolean("enabled",false).commit()
            WorkManager.getInstance(context).cancelAllWorkByTag("cloud-sync")
            vm.runTask { _ -> snapshot?.let { s ->
                val result = credentials.request(credentials.prefs.getString("server",null)!!+"/v1/collections/${s.collectionId}",token=credentials.accessToken(),method="DELETE")
                credentials.prefs.edit().remove("hash:${s.collectionId}").putLong("revision:${s.collectionId}",result.getLong("revision")).commit()
                File(context.filesDir,"sync-checkpoints/${s.collectionId}.json").delete()
                vm.message.value="远程集合已删除，云同步已关闭"
            } }
        }){Text("删除")}}, dismissButton={TextButton(onClick={confirm=false}){Text("取消")}})
}
