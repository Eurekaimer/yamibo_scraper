package com.yamibo.mobile.data

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import okhttp3.FormBody
import okhttp3.JavaNetCookieJar
import okhttp3.OkHttpClient
import okhttp3.Request
import org.jsoup.Jsoup
import org.jsoup.nodes.Element
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.CookieManager
import java.net.CookiePolicy
import java.net.HttpCookie
import java.net.URI
import java.net.URLEncoder
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.roundToLong
import kotlin.random.Random

private const val RETRY_JITTER_MS_MAX = 800L
private const val MIN_CATALOG_CHAPTERS = 3
private const val FAILED_MARKER_PREFIX = "#FAILED_CHAPTER_"
private const val DEFAULT_USER_AGENT =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

private data class SearchMutable(
    var title: String,
    var url: String,
    var forumId: Int?,
    var forumName: String,
    var replies: Int,
    var views: Int,
    var replyRank: Int,
    var viewRank: Int
)

private data class SaveTarget(
    val absolutePath: String,
    val displayPath: String,
    val savedToDownloads: Boolean,
    val localFallbackPath: String?
)

private data class RetryPolicy(
    val maxAttempts: Int,
    val initialDelayMs: Long,
    val maxDelayMs: Long,
    val backoffMultiplier: Double
)

private data class PageFetchResult(
    val html: String,
    val finalUrl: String
)

class YamiboClient(
    private val context: Context,
    private val userAgent: String = DEFAULT_USER_AGENT
) {
    private val forumNameMap = mapOf(
        49 to "文学区",
        55 to "译文区"
    )

    private val cookieManager = CookieManager(null, CookiePolicy.ACCEPT_ALL)
    private val client = OkHttpClient.Builder()
        .cookieJar(JavaNetCookieJar(cookieManager))
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(12, TimeUnit.SECONDS)
        .writeTimeout(12, TimeUnit.SECONDS)
        .callTimeout(18, TimeUnit.SECONDS)
        .build()

    fun clearCookies() {
        cookieManager.cookieStore.removeAll()
    }

    fun importCookieString(rawCookie: String) {
        clearCookies()
        val baseUri = URI(BASE_URL)
        rawCookie.split(";")
            .map { it.trim() }
            .filter { it.contains("=") }
            .forEach { kv ->
                val index = kv.indexOf('=')
                if (index <= 0) {
                    return@forEach
                }
                val name = kv.substring(0, index).trim()
                val value = kv.substring(index + 1).trim()
                if (name.isBlank()) {
                    return@forEach
                }

                val cookie = HttpCookie(name, value)
                cookie.domain = "bbs.yamibo.com"
                cookie.path = "/"
                cookie.isHttpOnly = false
                cookieManager.cookieStore.add(baseUri, cookie)
            }
    }

    fun loginWithPassword(username: String, password: String): Boolean {
        clearCookies()

        val loginPageUrl = "${BASE_URL}member.php?mod=logging&action=login"
        val loginHtml = getText(loginPageUrl)
        val doc = Jsoup.parse(loginHtml, BASE_URL)

        val loginForm = doc.selectFirst("form#loginform_Lz0")
            ?: doc.selectFirst("form#loginform")
            ?: doc.selectFirst("form[action*=mod=logging][action*=action=login]")
            ?: doc.selectFirst("form[id*=login], form[id*=Login], form[id*=LOGIN]")

        val actionUrl = when {
            loginForm == null -> "${BASE_URL}member.php?mod=logging&action=login&loginsubmit=yes"
            else -> {
                val action = loginForm.attr("action")
                if (action.isNullOrBlank()) {
                    "${BASE_URL}member.php?mod=logging&action=login&loginsubmit=yes"
                } else {
                    normalizeUrl(action)
                }
            }
        }

        val formhash = loginForm?.selectFirst("input[name=formhash]")?.attr("value")
            ?.takeIf { it.isNotBlank() }
            ?: doc.selectFirst("input[name=formhash]")?.attr("value")?.takeIf { it.isNotBlank() }
            ?: Regex("""formhash"\s+value="([a-zA-Z0-9]+)""")
                .find(loginHtml)
                ?.groupValues
                ?.getOrNull(1)
            ?: throw IllegalStateException("未能提取登录 formhash，请检查登录页面结构")

        val body = FormBody.Builder()
            .add("formhash", formhash)
            .add("referer", "${BASE_URL}forum.php")
            .add("loginfield", "username")
            .add("username", username)
            .add("password", password)
            .add("questionid", "0")
            .add("answer", "")
            .add("loginsubmit", "true")
            .build()

        post(actionUrl, body, "${BASE_URL}forum.php")

        val profileHtml = getText("${BASE_URL}home.php?mod=space")
        if (profileHtml.contains(username)) {
            return true
        }

        val cookieNames = cookieManager.cookieStore.cookies
            .map { it.name.lowercase(Locale.ROOT) }

        return cookieNames.any { it == "auth" || it.endsWith("_auth") }
    }

    fun searchThreads(keyword: String, forumIds: List<Int>, limit: Int = 20): List<SearchResult> {
        val query = URLEncoder.encode(keyword, Charsets.UTF_8.name())
        val forumSet = forumIds.toSet()
        val resultMap = linkedMapOf<String, SearchMutable>()

        for (orderKey in listOf("replies", "views")) {
            for (fid in forumIds) {
                val beforeCount = resultMap.size
                val urls = listOf(
                    "${BASE_URL}search.php?mod=forum&searchsubmit=yes&srchfid%5B%5D=$fid&orderby=$orderKey&ascdesc=desc&srchtxt=$query&kw=$query",
                    "${BASE_URL}search.php?mod=forum&searchsubmit=yes&srchfid%5B%5D=$fid&orderby=$orderKey&ascdesc=desc&srchtxt=$query"
                )

                var found = false
                for (url in urls) {
                    try {
                        val html = getText(url)
                        val doc = Jsoup.parse(html, BASE_URL)
                        collectResultsFromDoc(doc, resultMap, forumSet, fid, orderKey)
                        Thread.sleep(Random.nextLong(120L, 260L))
                        if (resultMap.size > beforeCount) {
                            found = true
                            break
                        }
                    } catch (_: Exception) {
                        // Keep best-effort behavior to avoid blocking the whole search.
                    }
                }
                if (found) {
                    continue
                }
            }
        }

        return resultMap.values
            .map {
                val replyRankScore = if (it.replyRank > 0) maxOf(0.0, 150.0 - it.replyRank) else 0.0
                val viewRankScore = if (it.viewRank > 0) maxOf(0.0, 120.0 - it.viewRank) else 0.0
                val rawScore = it.replies * 3.0 + it.views
                val popularity = rawScore + replyRankScore * 100 + viewRankScore * 60
                SearchResult(
                    title = it.title,
                    url = it.url,
                    forumId = it.forumId,
                    forumName = it.forumName,
                    replies = it.replies,
                    views = it.views,
                    replyRank = it.replyRank,
                    viewRank = it.viewRank,
                    popularityScore = popularity
                )
            }
            .sortedWith(
                compareByDescending<SearchResult> { it.popularityScore }
                    .thenBy { if (it.replyRank == 0) Int.MAX_VALUE else it.replyRank }
                    .thenBy { if (it.viewRank == 0) Int.MAX_VALUE else it.viewRank }
                    .thenByDescending { it.replies }
                    .thenByDescending { it.views }
            )
            .take(limit)
    }

    fun extractCatalogCandidatesFromThread(threadUrl: String): List<CatalogCandidate> {
        val html = getText(threadUrl)
        val doc = Jsoup.parse(html, BASE_URL)

        val nodes = mutableListOf<Pair<String, Element>>()

        doc.select("div.showcollapse_content").forEach { node ->
            if (node.selectFirst("a[href*=findpost], a[href*=pid=], a[href*=viewthread]") != null) {
                nodes += "showcollapse" to node
            }
        }

        listOf(
            "table",
            "tbody",
            "div#postlist",
            "div[id^=postmessage_]",
            "td[id^=postmessage_]",
            "div.pcb"
        ).forEach { selector ->
            doc.select(selector).forEach { node ->
                if (node.selectFirst("a[href*=viewthread], a[href*=mod=viewthread], a[href*=findpost], a[href*=pid=]") != null) {
                    nodes += selector to node
                }
            }
        }

        val signatureSeen = mutableSetOf<String>()
        val candidates = mutableListOf<CatalogCandidate>()

        nodes.forEachIndexed { index, (selector, node) ->
            val chapters = extractChaptersFromElement(node)
            if (chapters.isEmpty()) {
                return@forEachIndexed
            }

            val signature = chapters
                .take(30)
                .joinToString("|") { if (it.pid.isNotBlank()) "pid:${it.pid}" else "url:${it.url}" }

            if (!signatureSeen.add(signature)) {
                return@forEachIndexed
            }

            val (score, detail) = scoreCatalogDetail(chapters, selector)
            candidates += CatalogCandidate(
                selector = "$selector#${index + 1}",
                chapters = chapters,
                chapterCount = chapters.size,
                score = score,
                scoreDetail = detail,
                sampleTitles = chapters.take(3).map { it.title }
            )
        }

        val fallbackNode = doc.selectFirst("div#postlist") ?: doc.body()
        val fallbackChapters = extractChaptersFromElement(fallbackNode)
        if (fallbackChapters.isNotEmpty()) {
            val (score, detail) = scoreCatalogDetail(fallbackChapters, "fallback-page")
            candidates += CatalogCandidate(
                selector = "fallback-page",
                chapters = fallbackChapters,
                chapterCount = fallbackChapters.size,
                score = score,
                scoreDetail = detail,
                sampleTitles = fallbackChapters.take(3).map { it.title }
            )
        }

        return candidates
            .sortedByDescending { it.score }
            .take(8)
    }

    suspend fun previewChapters(
        chapters: List<Chapter>,
        previewCount: Int,
        snippetLength: Int = 120
    ): Pair<List<PreviewItem>, Map<Int, String>> {
        val retryPolicy = retryPolicyForSpeed(SpeedMode.FAST)
        val pidContentCache = mutableMapOf<String, String>()
        val count = previewCount.coerceAtLeast(1).coerceAtMost(chapters.size)
        val previewItems = mutableListOf<PreviewItem>()
        val cache = mutableMapOf<Int, String>()

        for (i in 0 until count) {
            val content = fetchChapterContent(
                url = chapters[i].url,
                retryPolicy = retryPolicy,
                pidContentCache = pidContentCache
            )
            cache[i] = content
            val snippet = content
                .replace(Regex("\\s+"), " ")
                .trim()
                .take(snippetLength)
            previewItems += PreviewItem(
                index = i,
                title = chapters[i].title,
                snippet = snippet
            )
        }

        return previewItems to cache
    }

    suspend fun crawlChaptersToTxt(
        chapters: List<Chapter>,
        outputTitle: String,
        speedMode: SpeedMode,
        previewCache: Map<Int, String>,
        allowLegacyDownloadWrite: Boolean,
        onProgress: (CrawlProgress) -> Unit,
        onNotice: ((String) -> Unit)? = null
    ): CrawlResult {
        val safeName = sanitizeFilename(outputTitle.ifBlank { "TITLE" })
        val fileName = "$safeName.txt"
        val retryPolicy = retryPolicyForSpeed(speedMode)
        val pidContentCache = ConcurrentHashMap<String, String>()
        val failedTitlesQueue = ConcurrentLinkedQueue<String>()
        val failedRecordQueue = ConcurrentLinkedQueue<FailedChapterRecord>()
        val startedAt = System.currentTimeMillis()
        val cacheHitCount = AtomicInteger(0)
        val doneCounter = AtomicInteger(0)
        if (speedMode.maxConcurrency > 1) {
            onNotice?.invoke("已启用并发抓取，最大并发 ${speedMode.maxConcurrency}。")
        }

        coroutineScope {
            val semaphore = Semaphore(speedMode.maxConcurrency)
            val jobs = chapters.mapIndexed { index, chapter ->
                async {
                    semaphore.withPermit {
                        val pid = chapter.pid
                        var usedNetwork = false

                        val previewContent = previewCache[index]
                        val content = if (previewContent != null) {
                            if (pid.isNotBlank()) {
                                pidContentCache[pid] = previewContent
                            }
                            previewContent
                        } else if (pid.isNotBlank() && pidContentCache.containsKey(pid)) {
                            cacheHitCount.incrementAndGet()
                            pidContentCache[pid].orEmpty()
                        } else {
                            usedNetwork = true
                            fetchChapterContent(
                                url = chapter.url,
                                retryPolicy = retryPolicy,
                                pidContentCache = pidContentCache
                            ) { nextAttempt, maxAttempts, waitMs, reason ->
                                onNotice?.invoke(
                                    "《${chapter.title}》请求失败，准备重试 $nextAttempt/$maxAttempts，等待 ${"%.1f".format(waitMs / 1000.0)}s：$reason"
                                )
                            }
                        }

                        val finalContent = if (content.startsWith("【最终失败")) {
                            val marker = "$FAILED_MARKER_PREFIX${index + 1}#"
                            failedTitlesQueue.add(chapter.title)
                            failedRecordQueue.add(
                                FailedChapterRecord(
                                    index = index,
                                    title = chapter.title,
                                    url = chapter.url,
                                    marker = marker
                                )
                            )
                            marker
                        } else {
                            content
                        }
                        chapter.content = finalContent

                        val done = doneCounter.incrementAndGet()
                        val elapsedSeconds = (System.currentTimeMillis() - startedAt) / 1000.0
                        val eta = if (done <= 0) 0L else {
                            ((elapsedSeconds / done) * (chapters.size - done)).roundToLong().coerceAtLeast(0)
                        }

                        onProgress(
                            CrawlProgress(
                                done = done,
                                total = chapters.size,
                                currentTitle = chapter.title,
                                etaSeconds = eta
                            )
                        )

                        if (done < chapters.size) {
                            val sleepMs = if (usedNetwork) {
                                Random.nextLong(speedMode.delayMinMs, speedMode.delayMaxMs + 1)
                            } else {
                                Random.nextLong(30L, 90L)
                            }
                            delay(sleepMs)
                        }
                    }
                }
            }
            jobs.awaitAll()
        }

        if (cacheHitCount.get() > 0) {
            onNotice?.invoke("目录页缓存命中 ${cacheHitCount.get()} 章，已减少重复请求。")
        }

        val text = buildString {
            chapters.forEach { chapter ->
                append("==== ${chapter.title} ====\n\n")
                append(chapter.content)
                append("\n\n\n")
            }
        }
        val localWorking = saveToAppPrivateOutput(fileName, text)

        val failedRecordsPath = if (failedRecordQueue.isNotEmpty()) {
            val failedFileName = "${safeName}.failed_chapters.json"
            val failedFile = saveFailedRecordsToAppPrivate(
                fileName = failedFileName,
                records = failedRecordQueue.toList().sortedBy { it.index }
            )
            failedFile.absolutePath
        } else {
            null
        }

        val saveTarget = writeTextToPreferredLocation(
            fileName = fileName,
            text = text,
            allowLegacyDownloadWrite = allowLegacyDownloadWrite
        )

        return CrawlResult(
            txtPath = saveTarget.absolutePath,
            displayPath = saveTarget.displayPath,
            fileName = fileName,
            savedToDownloads = saveTarget.savedToDownloads,
            localWorkingPath = localWorking.absolutePath,
            failedRecordsPath = failedRecordsPath,
            localFallbackPath = saveTarget.localFallbackPath,
            chapterCount = chapters.size,
            failedCount = failedTitlesQueue.size,
            failedTitles = failedTitlesQueue.toList()
        )
    }

    suspend fun retryFailedAndPatch(
        localWorkingPath: String,
        failedRecordsPath: String,
        speedMode: SpeedMode,
        onNotice: ((String) -> Unit)? = null
    ): RetryFillResult {
        val txtFile = File(localWorkingPath)
        if (!txtFile.exists()) {
            throw IllegalStateException("本地工作TXT不存在: $localWorkingPath")
        }
        val recordFile = File(failedRecordsPath)
        if (!recordFile.exists()) {
            throw IllegalStateException("失败章节记录不存在: $failedRecordsPath")
        }

        val records = loadFailedRecords(recordFile).sortedBy { it.index }
        if (records.isEmpty()) {
            return RetryFillResult(
                total = 0,
                succeeded = 0,
                remaining = 0,
                localWorkingPath = txtFile.absolutePath,
                failedRecordsPath = null,
                remainingTitles = emptyList()
            )
        }

        var txtContent = txtFile.readText(Charsets.UTF_8)
        val retryPolicy = retryPolicyForSpeed(speedMode)
        val pidCache = ConcurrentHashMap<String, String>()
        val remaining = mutableListOf<FailedChapterRecord>()
        var successCount = 0

        records.forEachIndexed { idx, record ->
            onNotice?.invoke("重试失败章节 ${idx + 1}/${records.size}: ${record.title}")
            val content = fetchChapterContent(
                url = record.url,
                retryPolicy = retryPolicy,
                pidContentCache = pidCache
            ) { nextAttempt, maxAttempts, waitMs, reason ->
                onNotice?.invoke(
                    "《${record.title}》回填重试 $nextAttempt/$maxAttempts，等待 ${"%.1f".format(waitMs / 1000.0)}s：$reason"
                )
            }
            if (content.startsWith("【最终失败")) {
                remaining += record
                return@forEachIndexed
            }

            if (!txtContent.contains(record.marker)) {
                // Marker may already be replaced by user/manual edits; skip silently.
                successCount += 1
                return@forEachIndexed
            }
            txtContent = txtContent.replace(record.marker, content)
            successCount += 1
        }

        txtFile.writeText(txtContent, Charsets.UTF_8)

        val remainingPath = if (remaining.isNotEmpty()) {
            val saved = saveFailedRecordsToAppPrivate(recordFile.name, remaining)
            saved.absolutePath
        } else {
            runCatching { recordFile.delete() }
            null
        }

        return RetryFillResult(
            total = records.size,
            succeeded = successCount,
            remaining = remaining.size,
            localWorkingPath = txtFile.absolutePath,
            failedRecordsPath = remainingPath,
            remainingTitles = remaining.map { it.title }
        )
    }

    fun exportFileToDownloads(
        sourcePath: String,
        outputFileName: String,
        allowLegacyDownloadWrite: Boolean
    ): ExportResult {
        val source = File(sourcePath)
        if (!source.exists() || !source.isFile) {
            throw IllegalStateException("待导出的文件不存在")
        }
        val text = source.readText(Charsets.UTF_8)
        val safe = sanitizeFilename(outputFileName).ifBlank { "TITLE" }
        val finalName = if (safe.lowercase(Locale.ROOT).endsWith(".txt")) safe else "$safe.txt"
        val saveTarget = writeTextToPreferredLocation(
            fileName = finalName,
            text = text,
            allowLegacyDownloadWrite = allowLegacyDownloadWrite
        )
        return ExportResult(
            savedToDownloads = saveTarget.savedToDownloads,
            displayPath = saveTarget.displayPath
        )
    }

    private fun writeTextToPreferredLocation(
        fileName: String,
        text: String,
        allowLegacyDownloadWrite: Boolean
    ): SaveTarget {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            saveToDownloadsByMediaStore(fileName, text)?.let { return it }
        } else if (allowLegacyDownloadWrite) {
            saveToLegacyDownloadDir(fileName, text)?.let { return it }
        }
        return saveToAppPrivateOutput(fileName, text)
    }

    private fun saveToDownloadsByMediaStore(fileName: String, text: String): SaveTarget? {
        return try {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                put(MediaStore.Downloads.MIME_TYPE, "text/plain")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null

            resolver.openOutputStream(uri)?.use { output ->
                output.write(text.toByteArray(Charsets.UTF_8))
                output.flush()
            } ?: return null

            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(uri, values, null, null)

            SaveTarget(
                absolutePath = uri.toString(),
                displayPath = "Download/$fileName",
                savedToDownloads = true,
                localFallbackPath = null
            )
        } catch (_: Exception) {
            null
        }
    }

    @Suppress("DEPRECATION")
    private fun saveToLegacyDownloadDir(fileName: String, text: String): SaveTarget? {
        return try {
            val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (!downloadsDir.exists()) {
                downloadsDir.mkdirs()
            }
            val output = File(downloadsDir, fileName)
            output.writeText(text, Charsets.UTF_8)
            SaveTarget(
                absolutePath = output.absolutePath,
                displayPath = output.absolutePath,
                savedToDownloads = true,
                localFallbackPath = output.absolutePath
            )
        } catch (_: Exception) {
            null
        }
    }

    private fun saveToAppPrivateOutput(fileName: String, text: String): SaveTarget {
        val outputDir = appOutputDir()
        val output = File(outputDir, fileName)
        output.writeText(text, Charsets.UTF_8)
        return SaveTarget(
            absolutePath = output.absolutePath,
            displayPath = output.absolutePath,
            savedToDownloads = false,
            localFallbackPath = output.absolutePath
        )
    }

    private fun appOutputDir(): File {
        val outputDir = File(context.getExternalFilesDir(null), "output")
        if (!outputDir.exists()) {
            outputDir.mkdirs()
        }
        return outputDir
    }

    private fun saveFailedRecordsToAppPrivate(
        fileName: String,
        records: List<FailedChapterRecord>
    ): File {
        val file = File(appOutputDir(), fileName)
        val array = JSONArray()
        records.forEach { item ->
            val obj = JSONObject()
            obj.put("index", item.index)
            obj.put("title", item.title)
            obj.put("url", item.url)
            obj.put("marker", item.marker)
            array.put(obj)
        }
        file.writeText(array.toString(2), Charsets.UTF_8)
        return file
    }

    private fun loadFailedRecords(file: File): List<FailedChapterRecord> {
        val raw = file.readText(Charsets.UTF_8)
        if (raw.isBlank()) {
            return emptyList()
        }
        val array = JSONArray(raw)
        val list = mutableListOf<FailedChapterRecord>()
        for (i in 0 until array.length()) {
            val obj = array.optJSONObject(i) ?: continue
            list += FailedChapterRecord(
                index = obj.optInt("index", -1).coerceAtLeast(0),
                title = obj.optString("title", "未知章节"),
                url = obj.optString("url", ""),
                marker = obj.optString("marker", "")
            )
        }
        return list.filter { it.url.isNotBlank() && it.marker.isNotBlank() }
    }

    private fun retryPolicyForSpeed(speedMode: SpeedMode): RetryPolicy {
        return when (speedMode) {
            SpeedMode.TURBO -> RetryPolicy(
                maxAttempts = 2,
                initialDelayMs = 120L,
                maxDelayMs = 700L,
                backoffMultiplier = 1.45
            )
            SpeedMode.FAST -> RetryPolicy(
                maxAttempts = 3,
                initialDelayMs = 250L,
                maxDelayMs = 1200L,
                backoffMultiplier = 1.6
            )
            SpeedMode.BALANCED -> RetryPolicy(
                maxAttempts = 4,
                initialDelayMs = 600L,
                maxDelayMs = 3200L,
                backoffMultiplier = 1.8
            )
            SpeedMode.GENTLE -> RetryPolicy(
                maxAttempts = 5,
                initialDelayMs = 1200L,
                maxDelayMs = 6000L,
                backoffMultiplier = 2.0
            )
        }
    }

    fun suggestMetaFromThreadTitle(rawTitle: String): Pair<String, String> {
        val title = rawTitle.trim()
        if (title.isBlank()) {
            return "TITLE" to "UNKNOWN"
        }

        val tags = Regex("[\\[【(](.*?)[\\]】)]").findAll(title).map { it.groupValues[1].trim() }.toList()
        val roleWords = listOf("个人翻译", "长篇", "短篇", "自翻", "授权转载", "转载", "生肉", "译文", "原创")
        var author = "UNKNOWN"
        for (tag in tags) {
            if (tag.isBlank()) {
                continue
            }
            if (roleWords.any { role -> tag.contains(role) }) {
                continue
            }
            if (Regex("[A-Za-z\u4e00-\u9fff]{2,}").containsMatchIn(tag)) {
                author = tag
                break
            }
        }

        val cleaned = title
            .replace(Regex("^(?:[\\[【(].*?[\\]】)])+"), "")
            .replace(Regex("[（(]?\\d{4}.*?更新.*?[)）]?\\s*$"), "")
            .replace(Regex("[（(]?.*?更新.*?[)）]?\\s*$"), "")
            .trim()
            .ifBlank { title }

        return cleaned to author
    }

    fun formatEta(seconds: Long): String {
        val safe = seconds.coerceAtLeast(0)
        val h = safe / 3600
        val m = (safe % 3600) / 60
        val s = safe % 60
        return if (h > 0) {
            String.format(Locale.ROOT, "%02d:%02d:%02d", h, m, s)
        } else {
            String.format(Locale.ROOT, "%02d:%02d", m, s)
        }
    }

    private fun collectResultsFromDoc(
        doc: org.jsoup.nodes.Document,
        resultMap: LinkedHashMap<String, SearchMutable>,
        forumSet: Set<Int>,
        fallbackFid: Int,
        orderKey: String
    ) {
        val anchors = doc.select("a.xst, a.s.xst, a[href*=mod=viewthread], a[href*=viewthread]")
        var rank = 0

        anchors.forEach { anchor ->
            val href = normalizeUrl(anchor.attr("href"))
            val title = anchor.text().trim()
            if (href.isBlank() || title.isBlank()) {
                return@forEach
            }
            if (!href.contains("viewthread")) {
                return@forEach
            }

            val forumInfo = extractForumInfo(anchor, fallbackFid)
            val forumId = forumInfo.first
            val forumName = forumInfo.second
            if (forumId != null && !forumSet.contains(forumId)) {
                return@forEach
            }

            val tid = extractTid(href)
            val uniqueKey = if (tid.isNotBlank()) "tid:$tid" else "url:$href"

            rank += 1
            val (replies, views) = extractThreadStats(anchor)

            val item = resultMap.getOrPut(uniqueKey) {
                SearchMutable(
                    title = title,
                    url = href,
                    forumId = forumId,
                    forumName = forumName,
                    replies = 0,
                    views = 0,
                    replyRank = 0,
                    viewRank = 0
                )
            }

            item.title = title
            item.url = href
            item.forumId = forumId
            item.forumName = forumName
            if (replies > item.replies) {
                item.replies = replies
            }
            if (views > item.views) {
                item.views = views
            }

            if (orderKey == "replies") {
                if (item.replyRank == 0 || rank < item.replyRank) {
                    item.replyRank = rank
                }
            } else {
                if (item.viewRank == 0 || rank < item.viewRank) {
                    item.viewRank = rank
                }
            }
        }
    }

    private fun extractForumInfo(anchor: Element, fallbackFid: Int): Pair<Int?, String> {
        var forumId: Int? = fallbackFid
        var forumName = forumNameMap[fallbackFid] ?: "未知分区"

        val row = anchor.parents().firstOrNull { it.tagName() == "tr" }
        val forumAnchor = row?.selectFirst("a[href*=forum-], a[href*=fid=]")
        if (forumAnchor != null) {
            val rowForumName = forumAnchor.text().trim()
            if (rowForumName.isNotBlank()) {
                forumName = rowForumName
            }
            val href = forumAnchor.attr("href")
            val m1 = Regex("forum-(\\d+)-").find(href)
            val m2 = Regex("[?&]fid=(\\d+)").find(href)
            val id = m1?.groupValues?.getOrNull(1)
                ?: m2?.groupValues?.getOrNull(1)
            if (!id.isNullOrBlank()) {
                forumId = id.toIntOrNull()
                forumName = forumNameMap[forumId] ?: forumName
            }
        }

        return forumId to forumName
    }

    private fun extractThreadStats(anchor: Element): Pair<Int, Int> {
        val row = anchor.parents().firstOrNull { it.tagName() == "tr" } ?: return 0 to 0

        val numCell = row.selectFirst("td.num, td[class*=num]")
        if (numCell != null) {
            val nums = Regex("\\d[\\d,]*").findAll(numCell.text()).map { safeInt(it.value) }.toList()
            if (nums.size >= 2) {
                return nums[0] to nums[1]
            }
            if (nums.size == 1) {
                return nums[0] to 0
            }
        }

        val values = mutableListOf<Int>()
        row.select("td span.xi1, td span.xw1, td em, td cite").forEach { node ->
            val value = safeInt(node.text())
            if (value > 0) {
                values += value
            }
        }
        return if (values.size >= 2) {
            values[0] to values[1]
        } else {
            0 to 0
        }
    }

    private fun extractChaptersFromElement(scope: Element): List<Chapter> {
        val chapters = mutableListOf<Chapter>()
        val seen = mutableSetOf<String>()

        val anchors = scope.select(
            "a[href*=viewthread], " +
                "a[href*=mod=viewthread], " +
                "a[href*=goto=findpost], " +
                "a[href*=findpost], " +
                "a[href*=pid=]"
        )

        anchors.forEachIndexed { _, anchor ->
            val rawHref = anchor.attr("href")
            val url = normalizeUrl(rawHref)
            if (url.isBlank()) {
                return@forEachIndexed
            }
            if (!url.contains("viewthread") && !url.contains("findpost") && !url.contains("pid=")) {
                return@forEachIndexed
            }

            val pid = extractPid(url)
            val unique = if (pid.isNotBlank()) "pid:$pid" else "url:$url"
            if (!seen.add(unique)) {
                return@forEachIndexed
            }

            var title = anchor.text().trim()
            if (isNoiseTitle(title)) {
                return@forEachIndexed
            }
            if (title.isBlank()) {
                title = "章节${chapters.size + 1}"
            }

            chapters += Chapter(
                title = title,
                url = url,
                pid = pid
            )
        }

        return chapters
    }

    private fun scoreCatalogDetail(chapters: List<Chapter>, selector: String): Pair<Double, CatalogScoreDetail> {
        if (chapters.isEmpty()) {
            return -1.0 to CatalogScoreDetail(
                base = 0.0,
                pidBonus = 0.0,
                titleBonus = 0.0,
                structureBonus = 0.0,
                sizeBonus = 0.0,
                qualityPenalty = 0.0,
                pidCount = 0,
                probableTitleCount = 0,
                suspiciousTitleCount = 0
            )
        }

        val base = chapters.size.toDouble()
        val pidCount = chapters.count { it.pid.isNotBlank() }
        val probableTitleCount = chapters.count { isProbableChapterTitle(it.title) }
        val suspiciousTitleCount = chapters.count {
            !isProbableChapterTitle(it.title) && Regex("[#\\[\\]【】复制链接只看举报楼主沙发板凳]", RegexOption.IGNORE_CASE).containsMatchIn(it.title)
        }

        val pidBonus = pidCount * 1.4
        val titleBonus = probableTitleCount * 1.8
        val structureBonus = when {
            selector.startsWith("showcollapse") || selector == "showcollapse" -> 26.0
            selector == "fallback-page" -> -24.0
            else -> 0.0
        }
        val sizeBonus = if (chapters.size >= MIN_CATALOG_CHAPTERS) 3.0 else 0.0
        val qualityPenalty = suspiciousTitleCount * 4.0

        val score = base + pidBonus + titleBonus + structureBonus + sizeBonus - qualityPenalty
        val detail = CatalogScoreDetail(
            base = base,
            pidBonus = pidBonus,
            titleBonus = titleBonus,
            structureBonus = structureBonus,
            sizeBonus = sizeBonus,
            qualityPenalty = qualityPenalty,
            pidCount = pidCount,
            probableTitleCount = probableTitleCount,
            suspiciousTitleCount = suspiciousTitleCount
        )

        return score to detail
    }

    private fun isProbableChapterTitle(title: String): Boolean {
        val t = title.trim().lowercase(Locale.ROOT)
        if (t.isBlank()) {
            return false
        }

        if (Regex("(episode|ep\\.?\\s*\\d+|chapter|ch\\.?\\s*\\d+)").containsMatchIn(t)) {
            return true
        }
        if (Regex("(第\\s*\\d+\\s*[话章节卷]|序章|终章|后记|番外|目录)").containsMatchIn(title)) {
            return true
        }
        if (Regex("^\\d{1,4}([#.]|\\s*话)?$").matches(t)) {
            return true
        }
        return false
    }

    private fun isNoiseTitle(title: String): Boolean {
        val t = title.trim()
        if (t.isBlank()) {
            return true
        }

        val noiseKeywords = listOf(
            "只看该作者",
            "只看大图",
            "评分",
            "收藏",
            "回复",
            "举报",
            "电梯直达",
            "使用道具",
            "道具",
            "发消息",
            "楼主",
            "沙发",
            "板凳",
            "复制链接",
            "复制代码",
            "查看原图",
            "倒序浏览"
        )
        return noiseKeywords.any { word -> t.contains(word) }
    }

    private fun sanitizeFilename(name: String): String {
        val step1 = name.trim().replace(Regex("[<>:\"/\\\\|?*]+"), "_")
        val step2 = step1.replace(Regex("\\s{2,}"), " ").trim(' ', '.')
        return if (step2.isBlank()) "TITLE" else step2
    }

    private fun normalizeUrl(href: String): String {
        val raw = href.trim().replace("&amp;", "&")
        if (raw.isBlank()) {
            return ""
        }
        if (raw.startsWith("javascript:")) {
            return ""
        }
        if (raw.startsWith("http://") || raw.startsWith("https://")) {
            return raw
        }
        if (raw.startsWith("forum.php")) {
            return BASE_URL + raw
        }
        if (raw.startsWith("./")) {
            return BASE_URL + raw.removePrefix("./")
        }
        if (raw.startsWith("/")) {
            return "https://bbs.yamibo.com$raw"
        }
        return BASE_URL + raw
    }

    private fun extractTid(url: String): String {
        val m1 = Regex("[?&]tid=(\\d+)").find(url)?.groupValues?.getOrNull(1)
        if (!m1.isNullOrBlank()) {
            return m1
        }
        val m2 = Regex("thread-(\\d+)-").find(url)?.groupValues?.getOrNull(1)
        return m2 ?: ""
    }

    private fun extractPid(url: String): String {
        val m = Regex("[?&]pid=(\\d+)").find(url)
        return m?.groupValues?.getOrNull(1) ?: ""
    }

    private fun safeInt(text: String): Int {
        val cleaned = text.replace(Regex("[^\\d]"), "")
        return cleaned.toIntOrNull() ?: 0
    }

    private fun getText(url: String, referer: String = "${BASE_URL}forum.php"): String {
        return getPage(url, referer).html
    }

    private fun getPage(url: String, referer: String = "${BASE_URL}forum.php"): PageFetchResult {
        val req = Request.Builder()
            .url(url)
            .header("User-Agent", userAgent)
            .header("Referer", referer)
            .header("Accept-Language", "zh-CN,zh;q=0.9")
            .get()
            .build()

        client.newCall(req).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("HTTP ${response.code}")
            }
            val html = response.body?.string().orEmpty()
            val finalUrl = response.request.url.toString()
            return PageFetchResult(
                html = html,
                finalUrl = finalUrl
            )
        }
    }

    private fun post(url: String, body: FormBody, referer: String): String {
        val req = Request.Builder()
            .url(url)
            .header("User-Agent", userAgent)
            .header("Referer", referer)
            .header("Accept-Language", "zh-CN,zh;q=0.9")
            .post(body)
            .build()

        client.newCall(req).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("HTTP ${response.code}")
            }
            return response.body?.string().orEmpty()
        }
    }

    private suspend fun fetchChapterContent(
        url: String,
        retryPolicy: RetryPolicy,
        pidContentCache: MutableMap<String, String>? = null,
        onRetry: ((nextAttempt: Int, maxAttempts: Int, waitMs: Long, reason: String) -> Unit)? = null
    ): String {
        val pid = extractPid(url)
        if (pid.isNotBlank()) {
            val cached = pidContentCache?.get(pid)
            if (!cached.isNullOrBlank()) {
                return cached
            }
        }

        var waitMs = retryPolicy.initialDelayMs

        for (attempt in 1..retryPolicy.maxAttempts) {
            try {
                val page = getPage(url)
                val doc = Jsoup.parse(page.html, BASE_URL)
                val batch = extractAllPostContents(doc)
                if (batch.isNotEmpty() && pidContentCache != null) {
                    batch.forEach { (k, v) ->
                        if (v.isNotBlank()) {
                            pidContentCache[k] = v
                        }
                    }
                }

                if (pid.isNotBlank()) {
                    val cached = pidContentCache?.get(pid)
                    if (!cached.isNullOrBlank()) {
                        return cached
                    }
                }

                val guardReason = detectRiskOrGuardPage(doc)
                if (!guardReason.isNullOrBlank()) {
                    throw IOException(guardReason)
                }

                if (pid.isNotBlank()) {
                    throw IllegalStateException("未找到目标章节 PID=$pid")
                }

                var contentNode: Element? = doc.selectFirst("td[id~=^postmessage_\\d+$]")
                if (contentNode == null) {
                    contentNode = doc.selectFirst("div[id~=^postmessage_\\d+$]")
                }
                if (contentNode == null) {
                    contentNode = doc.selectFirst("div.pcb, td.t_f, div.t_f")
                }
                if (contentNode == null) {
                    throw IllegalStateException("正文未找到")
                }

                return textFromContentNode(contentNode)
            } catch (e: Exception) {
                val reason = (e.message ?: "unknown").trim()
                if (isNonRetriable(reason)) {
                    return "【最终失败：$reason】"
                }
                if (attempt >= retryPolicy.maxAttempts) {
                    return "【最终失败：$reason】"
                }

                val jitter = Random.nextLong(0, RETRY_JITTER_MS_MAX + 1)
                var finalWaitMs = waitMs + jitter
                if (isLikelyGuardReason(reason)) {
                    finalWaitMs = maxOf(finalWaitMs, 2800L)
                }
                onRetry?.invoke(
                    attempt + 1,
                    retryPolicy.maxAttempts,
                    finalWaitMs,
                    reason
                )
                delay(finalWaitMs)
                waitMs = (waitMs * retryPolicy.backoffMultiplier).toLong().coerceAtMost(retryPolicy.maxDelayMs)
            }
        }

        return "【最终失败：未知错误】"
    }

    private fun textFromContentNode(node: Element): String {
        val cloned = node.clone()
        cloned.select("i.pstatus, script, style").remove()

        var text = cloned.wholeText()
            .replace("\r\n", "\n")
            .replace(Regex("\n{3,}"), "\n\n")
            .trim()
        if (text.replace(Regex("\\s+"), "").length < 20) {
            text = cloned.text().replace(Regex("\\s{2,}"), " ").trim()
        }
        if (text.replace(Regex("\\s+"), "").length < 20) {
            throw IllegalStateException("正文内容过短，疑似未命中正文区域")
        }
        return text
    }

    private fun extractAllPostContents(doc: org.jsoup.nodes.Document): Map<String, String> {
        val result = linkedMapOf<String, String>()
        val nodes = doc.select("td[id~=^postmessage_\\d+$], div[id~=^postmessage_\\d+$]")
        for (node in nodes) {
            val id = node.id()
            val pid = Regex("^postmessage_(\\d+)$").find(id)?.groupValues?.getOrNull(1) ?: continue
            runCatching { textFromContentNode(node) }
                .getOrNull()
                ?.takeIf { it.isNotBlank() }
                ?.let { result[pid] = it }
        }
        return result
    }

    private fun detectRiskOrGuardPage(doc: org.jsoup.nodes.Document): String? {
        val text = doc.text()
        if (text.isBlank()) {
            return null
        }
        val keywords = listOf(
            "验证码",
            "安全验证",
            "访问过于频繁",
            "请稍后再试",
            "请求过于频繁",
            "需要登录后查看",
            "您无权进行当前操作",
            "Cloudflare",
            "Attention Required"
        )
        return if (keywords.any { text.contains(it, ignoreCase = true) }) {
            "疑似触发风控/权限限制页面"
        } else {
            null
        }
    }

    private fun isNonRetriable(reason: String): Boolean {
        val r = reason.lowercase(Locale.ROOT)
        return r.contains("http 400")
            || r.contains("http 401")
            || r.contains("http 403")
            || r.contains("http 404")
            || r.contains("http 410")
            || r.contains("http 422")
            || r.contains("未找到目标章节 pid")
    }

    private fun isLikelyGuardReason(reason: String): Boolean {
        val r = reason.lowercase(Locale.ROOT)
        return r.contains("验证码")
            || r.contains("风控")
            || r.contains("过于频繁")
            || r.contains("cloudflare")
            || r.contains("attention required")
    }
}
