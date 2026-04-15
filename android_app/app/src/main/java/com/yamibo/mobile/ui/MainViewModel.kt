package com.yamibo.mobile.ui

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.yamibo.mobile.data.AuthMode
import com.yamibo.mobile.data.CatalogCandidate
import com.yamibo.mobile.data.ForumScope
import com.yamibo.mobile.data.PreviewItem
import com.yamibo.mobile.data.SavedOutputFile
import com.yamibo.mobile.data.SearchResult
import com.yamibo.mobile.data.SpeedMode
import com.yamibo.mobile.data.YamiboClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.max

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val prefs = application.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)

    var userAgent by mutableStateOf(DEFAULT_UA)
    var authMode by mutableStateOf(AuthMode.ACCOUNT)
    var username by mutableStateOf("")
    var password by mutableStateOf("")
    var cookie by mutableStateOf("")
    var rememberAuth by mutableStateOf(true)
    var loginStatusText by mutableStateOf("未登录")
    var loginStatusOk by mutableStateOf(false)

    var keyword by mutableStateOf("")
    var forumScope by mutableStateOf(ForumScope.BOTH)

    var speedMode by mutableStateOf(SpeedMode.FAST)
        private set
    private var liveSpeedMode: SpeedMode = SpeedMode.FAST

    var previewCountText by mutableStateOf("2")
    var outputTitle by mutableStateOf("")
    var outputAuthor by mutableStateOf("")
    var enableOverlay by mutableStateOf(false)

    var searchResults by mutableStateOf(emptyList<SearchResult>())
    var selectedSearchIndex by mutableStateOf(-1)

    var catalogCandidates by mutableStateOf(emptyList<CatalogCandidate>())
    var selectedCandidateIndex by mutableStateOf(-1)

    var previewItems by mutableStateOf(emptyList<PreviewItem>())
    private var previewCache: Map<Int, String> = emptyMap()
    var previewConfirmed by mutableStateOf(false)

    var isBusy by mutableStateOf(false)
    var status by mutableStateOf("待命")
    var progressText by mutableStateOf("")
    var outputPath by mutableStateOf("")
    var outputSavedToDownloads by mutableStateOf(false)
    private var outputLocalFallbackPath: String? = null
    private var latestLocalWorkingPath: String? = null
    private var latestFailedRecordsPath: String? = null
    var latestFailedCount by mutableStateOf(0)
    var latestFailedTitles by mutableStateOf(emptyList<String>())
    var legacyStoragePermissionGranted by mutableStateOf(false)

    var savedFiles by mutableStateOf(emptyList<SavedOutputFile>())
    var selectedSavedFileIndex by mutableStateOf(-1)

    var logs by mutableStateOf(emptyList<String>())

    private var client: YamiboClient? = null
    private var authenticated = false
    private var lastProgressUpdateMs: Long = 0L
    private var lastNoticeUpdateMs: Long = 0L
    private var lastNoticeText: String = ""

    init {
        restorePrefs()
        refreshSavedFiles()
    }

    private fun appendLog(text: String) {
        if (logs.lastOrNull() == text) {
            status = text
            return
        }
        logs = (logs + text).takeLast(220)
        status = text
    }

    private fun parsePreviewCount(): Int {
        return previewCountText.trim().toIntOrNull()?.coerceAtLeast(1) ?: 2
    }

    private fun ensureClient(forceReset: Boolean = false): YamiboClient {
        if (forceReset || client == null) {
            client = YamiboClient(
                context = getApplication(),
                userAgent = userAgent.ifBlank { DEFAULT_UA }
            )
            authenticated = false
        }
        return client!!
    }

    private fun restorePrefs() {
        userAgent = prefs.getString(KEY_USER_AGENT, DEFAULT_UA) ?: DEFAULT_UA
        authMode = parseAuthMode(prefs.getString(KEY_AUTH_MODE, AuthMode.ACCOUNT.name))
        rememberAuth = prefs.getBoolean(KEY_REMEMBER_AUTH, true)
        if (rememberAuth) {
            username = prefs.getString(KEY_USERNAME, "").orEmpty()
            password = prefs.getString(KEY_PASSWORD, "").orEmpty()
            cookie = prefs.getString(KEY_COOKIE, "").orEmpty()
        } else {
            username = ""
            password = ""
            cookie = ""
        }
        keyword = prefs.getString(KEY_KEYWORD, "").orEmpty()
        forumScope = parseForumScope(prefs.getString(KEY_FORUM_SCOPE, ForumScope.BOTH.name))
        speedMode = parseSpeedMode(prefs.getString(KEY_SPEED_MODE, SpeedMode.FAST.name))
        liveSpeedMode = speedMode
        previewCountText = prefs.getString(KEY_PREVIEW_COUNT, "2").orEmpty().ifBlank { "2" }
        outputTitle = prefs.getString(KEY_OUTPUT_TITLE, "").orEmpty()
        outputAuthor = prefs.getString(KEY_OUTPUT_AUTHOR, "").orEmpty()
        enableOverlay = prefs.getBoolean(KEY_ENABLE_OVERLAY, false)
    }

    fun persistNow() {
        val editor = prefs.edit()
        editor.putString(KEY_USER_AGENT, userAgent)
        editor.putString(KEY_AUTH_MODE, authMode.name)
        editor.putBoolean(KEY_REMEMBER_AUTH, rememberAuth)
        if (rememberAuth) {
            editor.putString(KEY_USERNAME, username)
            editor.putString(KEY_PASSWORD, password)
            editor.putString(KEY_COOKIE, cookie)
        } else {
            editor.remove(KEY_USERNAME)
            editor.remove(KEY_PASSWORD)
            editor.remove(KEY_COOKIE)
        }
        editor.putString(KEY_KEYWORD, keyword)
        editor.putString(KEY_FORUM_SCOPE, forumScope.name)
        editor.putString(KEY_SPEED_MODE, speedMode.name)
        editor.putString(KEY_PREVIEW_COUNT, previewCountText)
        editor.putString(KEY_OUTPUT_TITLE, outputTitle)
        editor.putString(KEY_OUTPUT_AUTHOR, outputAuthor)
        editor.putBoolean(KEY_ENABLE_OVERLAY, enableOverlay)
        editor.apply()
    }

    fun resetSession() {
        client = null
        authenticated = false
        loginStatusText = "未登录"
        loginStatusOk = false
        appendLog("会话已重置")
    }

    fun setLegacyStoragePermission(granted: Boolean) {
        legacyStoragePermissionGranted = granted
    }

    fun setAuthMode(mode: AuthMode) {
        authMode = mode
        persistNow()
    }

    fun setRememberAuth(remember: Boolean) {
        rememberAuth = remember
        if (!remember) {
            username = ""
            password = ""
            cookie = ""
            authenticated = false
        }
        persistNow()
    }

    fun setForumScope(scope: ForumScope) {
        forumScope = scope
        persistNow()
    }

    fun setSpeedMode(mode: SpeedMode) {
        speedMode = mode
        liveSpeedMode = mode
        persistNow()
        if (isBusy) {
            appendLog("已切换速度：${mode.label}（下一章生效）")
        }
    }

    fun setOverlayEnabled(enabled: Boolean) {
        enableOverlay = enabled
        persistNow()
    }

    private suspend fun ensureAuthenticated(authRequired: Boolean = true, forceReset: Boolean = false): YamiboClient {
        val c = ensureClient(forceReset)
        if (authenticated) {
            return c
        }

        if (authMode == AuthMode.ACCOUNT) {
            val u = username.trim()
            val p = password
            if (u.isBlank() || p.isBlank()) {
                if (authRequired) {
                    throw IllegalStateException("账号模式下必须输入账号和密码")
                }
                return c
            }
            val ok = withContext(Dispatchers.IO) { c.loginWithPassword(u, p) }
            if (!ok) {
                throw IllegalStateException("账号密码登录失败")
            }
            authenticated = true
            loginStatusText = "账号登录成功"
            loginStatusOk = true
            appendLog("账号登录成功")
            persistNow()
            return c
        }

        val rawCookie = cookie.trim()
        if (rawCookie.isBlank()) {
            if (authRequired) {
                throw IllegalStateException("Cookie 模式下必须输入 Cookie")
            }
            return c
        }

        c.importCookieString(rawCookie)
        authenticated = true
        loginStatusText = "Cookie 已载入"
        loginStatusOk = true
        appendLog("Cookie 已载入")
        persistNow()
        return c
    }

    fun doLogin() {
        if (isBusy) {
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                persistNow()
                ensureAuthenticated(authRequired = true, forceReset = true)
                if (loginStatusText == "未登录") {
                    loginStatusText = "登录完成"
                    loginStatusOk = true
                }
                appendLog("登录完成")
            } catch (e: Exception) {
                loginStatusText = "登录失败: ${e.message}"
                loginStatusOk = false
                appendLog("登录失败: ${e.message}")
            } finally {
                isBusy = false
            }
        }
    }

    fun searchThreads() {
        if (isBusy) {
            return
        }

        val kw = keyword.trim()
        if (kw.isBlank()) {
            appendLog("请先输入关键词")
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                persistNow()
                val c = ensureAuthenticated(authRequired = true)
                val results = withContext(Dispatchers.IO) {
                    c.searchThreads(
                        keyword = kw,
                        forumIds = forumScope.ids,
                        limit = 25
                    )
                }
                searchResults = results
                selectedSearchIndex = if (results.isNotEmpty()) 0 else -1
                catalogCandidates = emptyList()
                selectedCandidateIndex = -1
                previewItems = emptyList()
                previewCache = emptyMap()
                previewConfirmed = false
                progressText = ""

                if (selectedSearchIndex >= 0) {
                    val selected = results[selectedSearchIndex]
                    if (outputTitle.isBlank() || outputAuthor.isBlank()) {
                        val (title, author) = c.suggestMetaFromThreadTitle(selected.title)
                        if (outputTitle.isBlank()) {
                            outputTitle = title
                        }
                        if (outputAuthor.isBlank()) {
                            outputAuthor = author
                        }
                    }
                }

                appendLog("搜索完成，共 ${results.size} 条")
            } catch (e: Exception) {
                appendLog("搜索失败: ${e.message}")
            } finally {
                isBusy = false
            }
        }
    }

    fun loadCatalogCandidates() {
        if (isBusy) {
            return
        }

        val selectedThread = searchResults.getOrNull(selectedSearchIndex)
        if (selectedThread == null) {
            appendLog("请先在搜索结果中选择一个帖子")
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                persistNow()
                val c = ensureAuthenticated(authRequired = true)
                val candidates = withContext(Dispatchers.IO) {
                    c.extractCatalogCandidatesFromThread(selectedThread.url)
                }

                catalogCandidates = candidates
                selectedCandidateIndex = if (candidates.isNotEmpty()) 0 else -1
                previewItems = emptyList()
                previewCache = emptyMap()
                previewConfirmed = false

                appendLog("目录候选已提取: ${candidates.size} 个")
            } catch (e: Exception) {
                appendLog("提取目录失败: ${e.message}")
            } finally {
                isBusy = false
            }
        }
    }

    fun previewChapters() {
        if (isBusy) {
            return
        }

        val selectedCandidate = catalogCandidates.getOrNull(selectedCandidateIndex)
        if (selectedCandidate == null) {
            appendLog("请先选择目录候选")
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                persistNow()
                val c = ensureAuthenticated(authRequired = true)
                val desiredCount = parsePreviewCount()
                val (previewList, cache) = withContext(Dispatchers.IO) {
                    c.previewChapters(selectedCandidate.chapters, desiredCount)
                }
                previewItems = previewList
                previewCache = cache
                previewConfirmed = false

                appendLog("预览完成，请确认内容后再开始抓取")
            } catch (e: Exception) {
                appendLog("预览失败: ${e.message}")
            } finally {
                isBusy = false
            }
        }
    }

    fun confirmPreview() {
        previewConfirmed = true
        appendLog("已确认预览，可开始抓取")
    }

    fun startCrawl() {
        if (isBusy) {
            return
        }

        val selectedCandidate = catalogCandidates.getOrNull(selectedCandidateIndex)
        if (selectedCandidate == null) {
            appendLog("请先选择目录候选")
            return
        }
        if (previewItems.isEmpty()) {
            appendLog("请先执行预览")
            return
        }
        if (!previewConfirmed) {
            appendLog("请先点击“确认预览无误”")
            return
        }

        viewModelScope.launch {
            isBusy = true
            progressText = ""
            outputPath = ""
            outputSavedToDownloads = false
            outputLocalFallbackPath = null
            latestLocalWorkingPath = null
            latestFailedRecordsPath = null
            latestFailedCount = 0
            latestFailedTitles = emptyList()
            lastProgressUpdateMs = 0L
            lastNoticeUpdateMs = 0L
            lastNoticeText = ""

            val app = getApplication<Application>()
            var overlayStarted = false
            try {
                persistNow()
                val c = ensureAuthenticated(authRequired = true)
                val chapters = selectedCandidate.chapters.map { it.copy() }
                val title = outputTitle.trim().ifBlank {
                    val selectedThread = searchResults.getOrNull(selectedSearchIndex)
                    if (selectedThread != null) {
                        c.suggestMetaFromThreadTitle(selectedThread.title).first
                    } else {
                        "TITLE"
                    }
                }

                appendLog("开始抓取，共 ${chapters.size} 章，当前速度：${speedMode.label}")
                DownloadOverlayService.start(app, "准备抓取：$title", enableOverlay)
                overlayStarted = true

                val result = withContext(Dispatchers.IO) {
                    c.crawlChaptersToTxt(
                        chapters = chapters,
                        outputTitle = title,
                        speedMode = speedMode,
                        previewCache = previewCache,
                        allowLegacyDownloadWrite = legacyStoragePermissionGranted,
                        onProgress = { p ->
                            val now = System.currentTimeMillis()
                            val shouldRefresh = p.done == p.total || now - lastProgressUpdateMs >= 350L
                            if (shouldRefresh) {
                                lastProgressUpdateMs = now
                                val etaText = c.formatEta(p.etaSeconds)
                                val line = "[${p.done}/${p.total}] ${p.currentTitle} | 预计剩余时间: $etaText"
                                DownloadOverlayService.update(
                                    app,
                                    p.currentTitle,
                                    p.done,
                                    p.total,
                                    etaText
                                )
                                viewModelScope.launch(Dispatchers.Main) {
                                    progressText = line
                                }
                            }
                        },
                        onNotice = { msg ->
                            val now = System.currentTimeMillis()
                            val tooFrequent = now - lastNoticeUpdateMs < 700L
                            if (!tooFrequent || msg != lastNoticeText) {
                                lastNoticeUpdateMs = now
                                lastNoticeText = msg
                                viewModelScope.launch(Dispatchers.Main) {
                                    appendLog(msg)
                                }
                            }
                        },
                        speedProvider = { liveSpeedMode }
                    )
                }

                outputPath = result.displayPath
                outputSavedToDownloads = result.savedToDownloads
                outputLocalFallbackPath = result.localFallbackPath ?: result.localWorkingPath
                latestLocalWorkingPath = result.localWorkingPath
                latestFailedRecordsPath = result.failedRecordsPath
                latestFailedCount = result.failedCount
                latestFailedTitles = result.failedTitles
                if (result.savedToDownloads) {
                    appendLog("抓取完成，已保存到 Download: ${result.displayPath}")
                } else {
                    appendLog("抓取完成，未能写入 Download，已回退保存到: ${result.displayPath}")
                }
                if (result.failedCount > 0) {
                    appendLog("有 ${result.failedCount} 章抓取失败，失败清单如下:")
                    result.failedTitles.forEachIndexed { idx, t ->
                        appendLog("失败[${idx + 1}]: $t")
                    }
                    result.failedRecordsPath?.let { path ->
                        appendLog("失败记录已保存: $path")
                    }
                }
                refreshSavedFiles()
            } catch (e: Exception) {
                appendLog("抓取失败: ${e.message}")
            } finally {
                if (overlayStarted) {
                    DownloadOverlayService.stop(app)
                }
                isBusy = false
                persistNow()
            }
        }
    }

    fun retryFailedAndPatch() {
        if (isBusy) {
            return
        }
        val localPath = latestLocalWorkingPath
        val failedPath = latestFailedRecordsPath
        if (localPath.isNullOrBlank() || failedPath.isNullOrBlank()) {
            appendLog("当前没有可回填的失败章节记录")
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                persistNow()
                val c = ensureAuthenticated(authRequired = true)
                appendLog("开始仅重试失败章节并回填（当前速度：${speedMode.label}）...")
                val result = withContext(Dispatchers.IO) {
                    c.retryFailedAndPatch(
                        localWorkingPath = localPath,
                        failedRecordsPath = failedPath,
                        speedMode = speedMode,
                        onNotice = { msg ->
                            viewModelScope.launch(Dispatchers.Main) {
                                appendLog(msg)
                            }
                        },
                        speedProvider = { liveSpeedMode }
                    )
                }
                latestLocalWorkingPath = result.localWorkingPath
                latestFailedRecordsPath = result.failedRecordsPath
                latestFailedCount = result.remaining
                latestFailedTitles = result.remainingTitles
                outputPath = result.localWorkingPath
                outputSavedToDownloads = false
                outputLocalFallbackPath = result.localWorkingPath

                appendLog("失败回填完成：成功 ${result.succeeded}/${result.total}，剩余 ${result.remaining}")
                if (result.remaining == 0) {
                    appendLog("所有失败章节已回填，可重新导出到 Download。")
                } else {
                    appendLog("剩余失败清单:")
                    result.remainingTitles.forEachIndexed { idx, t ->
                        appendLog("剩余[${idx + 1}]: $t")
                    }
                    appendLog("仍有失败章节，稍后可再次重试。")
                }
                refreshSavedFiles()
            } catch (e: Exception) {
                appendLog("失败章节回填失败: ${e.message}")
            } finally {
                isBusy = false
                persistNow()
            }
        }
    }

    fun exportLatestToDownloads() {
        if (isBusy) {
            return
        }
        if (outputSavedToDownloads) {
            appendLog("当前文件已经在 Download 目录，无需再次导出")
            return
        }
        val source = outputLocalFallbackPath
        if (source.isNullOrBlank()) {
            appendLog("没有可导出的本地文件，请先完成一次抓取")
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                persistNow()
                val c = ensureAuthenticated(authRequired = false)
                val desiredName = outputTitle.trim().ifBlank { "TITLE" }
                val exported = withContext(Dispatchers.IO) {
                    c.exportFileToDownloads(
                        sourcePath = source,
                        outputFileName = desiredName,
                        allowLegacyDownloadWrite = legacyStoragePermissionGranted
                    )
                }
                outputPath = exported.displayPath
                outputSavedToDownloads = exported.savedToDownloads
                outputLocalFallbackPath = exported.localFallbackPath ?: source
                if (exported.savedToDownloads) {
                    appendLog("导出成功: ${exported.displayPath}")
                } else {
                    appendLog("导出失败，仍保留在应用目录")
                }
                refreshSavedFiles()
            } catch (e: Exception) {
                appendLog("导出失败: ${e.message}")
            } finally {
                isBusy = false
                persistNow()
            }
        }
    }

    fun convertSelectedTxtToEpub() {
        if (isBusy) {
            return
        }
        val selected = savedFiles.getOrNull(selectedSavedFileIndex)
        if (selected == null) {
            appendLog("请先在文件列表里选择一个 TXT")
            return
        }
        if (!selected.name.lowercase().endsWith(".txt")) {
            appendLog("当前选中的不是 TXT 文件，无法转换 EPUB")
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                persistNow()
                val c = ensureAuthenticated(authRequired = false)
                val bookTitle = outputTitle.trim().ifBlank {
                    selected.name.substringBeforeLast(".")
                }
                val bookAuthor = outputAuthor.trim().ifBlank { "UNKNOWN" }
                val result = withContext(Dispatchers.IO) {
                    c.convertTxtToEpub(
                        sourcePath = selected.absolutePath,
                        outputTitle = bookTitle,
                        outputAuthor = bookAuthor,
                        allowLegacyDownloadWrite = legacyStoragePermissionGranted
                    )
                }
                outputPath = result.displayPath
                outputSavedToDownloads = result.savedToDownloads
                outputLocalFallbackPath = result.localFallbackPath
                appendLog("EPUB 转换完成: ${result.displayPath}")
                refreshSavedFiles()
            } catch (e: Exception) {
                appendLog("EPUB 转换失败: ${e.message}")
            } finally {
                isBusy = false
                persistNow()
            }
        }
    }

    fun refreshSavedFiles() {
        viewModelScope.launch {
            val c = ensureClient(forceReset = false)
            val list = withContext(Dispatchers.IO) {
                c.listSavedOutputFiles()
            }
            savedFiles = list
            if (savedFiles.isEmpty()) {
                selectedSavedFileIndex = -1
            } else if (selectedSavedFileIndex !in savedFiles.indices) {
                selectedSavedFileIndex = 0
            }
        }
    }

    fun chooseSavedFile(index: Int) {
        selectedSavedFileIndex = max(-1, index)
    }

    fun openSelectedFile() {
        val selected = savedFiles.getOrNull(selectedSavedFileIndex)
        if (selected == null) {
            appendLog("请先在列表中选择文件")
            return
        }
        val c = ensureClient(forceReset = false)
        val ok = c.openFileWithSystem(selected.absolutePath)
        if (ok) {
            appendLog("已调用系统打开: ${selected.name}")
        } else {
            appendLog("打开失败，请确认设备已安装可读取该格式的应用")
        }
    }

    fun openLatestOutput() {
        val path = outputLocalFallbackPath ?: latestLocalWorkingPath
        if (path.isNullOrBlank()) {
            appendLog("当前没有可打开的抓取文件")
            return
        }
        val c = ensureClient(forceReset = false)
        val ok = c.openFileWithSystem(path)
        if (ok) {
            appendLog("已调用系统打开最新文件")
        } else {
            appendLog("打开失败，请检查文件是否存在")
        }
    }

    fun clearLogs() {
        logs = emptyList()
        status = "日志已清空"
    }

    fun chooseSearchResult(index: Int) {
        selectedSearchIndex = max(-1, index)
        previewConfirmed = false
    }

    fun chooseCatalogCandidate(index: Int) {
        selectedCandidateIndex = max(-1, index)
        previewItems = emptyList()
        previewCache = emptyMap()
        previewConfirmed = false
    }

    private fun parseAuthMode(raw: String?): AuthMode {
        return AuthMode.entries.firstOrNull { it.name == raw } ?: AuthMode.ACCOUNT
    }

    private fun parseForumScope(raw: String?): ForumScope {
        return ForumScope.entries.firstOrNull { it.name == raw } ?: ForumScope.BOTH
    }

    private fun parseSpeedMode(raw: String?): SpeedMode {
        return SpeedMode.entries.firstOrNull { it.name == raw } ?: SpeedMode.FAST
    }

    companion object {
        private const val PREF_NAME = "yamibo_mobile_config"
        private const val KEY_USER_AGENT = "user_agent"
        private const val KEY_AUTH_MODE = "auth_mode"
        private const val KEY_USERNAME = "username"
        private const val KEY_PASSWORD = "password"
        private const val KEY_COOKIE = "cookie"
        private const val KEY_REMEMBER_AUTH = "remember_auth"
        private const val KEY_KEYWORD = "keyword"
        private const val KEY_FORUM_SCOPE = "forum_scope"
        private const val KEY_SPEED_MODE = "speed_mode"
        private const val KEY_PREVIEW_COUNT = "preview_count"
        private const val KEY_OUTPUT_TITLE = "output_title"
        private const val KEY_OUTPUT_AUTHOR = "output_author"
        private const val KEY_ENABLE_OVERLAY = "enable_overlay"
        private const val DEFAULT_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
}

