package com.yamibo.mobile.ui

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.yamibo.mobile.data.AuthMode
import com.yamibo.mobile.data.CatalogCandidate
import com.yamibo.mobile.data.ForumScope
import com.yamibo.mobile.data.PreviewItem
import com.yamibo.mobile.data.SearchResult
import com.yamibo.mobile.data.SpeedMode
import com.yamibo.mobile.data.YamiboClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.max

class MainViewModel(application: Application) : AndroidViewModel(application) {
    var userAgent by mutableStateOf(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    var authMode by mutableStateOf(AuthMode.ACCOUNT)
    var username by mutableStateOf("")
    var password by mutableStateOf("")
    var cookie by mutableStateOf("")

    var keyword by mutableStateOf("")
    var forumScope by mutableStateOf(ForumScope.BOTH)

    var speedMode by mutableStateOf(SpeedMode.FAST)
    var previewCountText by mutableStateOf("2")
    var outputTitle by mutableStateOf("")
    var outputAuthor by mutableStateOf("")

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
    var legacyStoragePermissionGranted by mutableStateOf(false)

    var logs by mutableStateOf(emptyList<String>())

    private var client: YamiboClient? = null
    private var authenticated = false

    private fun appendLog(text: String) {
        logs = (logs + text).takeLast(500)
        status = text
    }

    private fun parsePreviewCount(): Int {
        return previewCountText.trim().toIntOrNull()?.coerceAtLeast(1) ?: 2
    }

    private fun ensureClient(forceReset: Boolean = false): YamiboClient {
        if (forceReset || client == null) {
            client = YamiboClient(
                context = getApplication(),
                userAgent = userAgent.ifBlank {
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                }
            )
            authenticated = false
        }
        return client!!
    }

    fun resetSession() {
        client = null
        authenticated = false
        appendLog("会话已重置")
    }

    fun setLegacyStoragePermission(granted: Boolean) {
        legacyStoragePermissionGranted = granted
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
            appendLog("账号登录成功")
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
        appendLog("Cookie 已载入")
        return c
    }

    fun doLogin() {
        if (isBusy) {
            return
        }

        viewModelScope.launch {
            isBusy = true
            try {
                ensureAuthenticated(authRequired = true, forceReset = true)
                appendLog("登录完成")
            } catch (e: Exception) {
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
            try {
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

                appendLog("开始抓取，共 ${chapters.size} 章，速度：${speedMode.label}")

                val result = withContext(Dispatchers.IO) {
                    c.crawlChaptersToTxt(
                        chapters = chapters,
                        outputTitle = title,
                        speedMode = speedMode,
                        previewCache = previewCache,
                        allowLegacyDownloadWrite = legacyStoragePermissionGranted
                    ) { p ->
                        val line = "[${p.done}/${p.total}] ${p.currentTitle} | 预计剩余时间: ${c.formatEta(p.etaSeconds)}"
                        viewModelScope.launch(Dispatchers.Main) {
                            progressText = line
                        }
                    }
                }

                outputPath = result.displayPath
                outputSavedToDownloads = result.savedToDownloads
                outputLocalFallbackPath = result.localFallbackPath
                if (result.savedToDownloads) {
                    appendLog("抓取完成，已保存到 Download: ${result.displayPath}")
                } else {
                    appendLog("抓取完成，未能写入 Download，已回退保存到: ${result.displayPath}")
                }
                if (result.failedCount > 0) {
                    appendLog("有 ${result.failedCount} 章抓取失败，请稍后重试")
                }
            } catch (e: Exception) {
                appendLog("抓取失败: ${e.message}")
            } finally {
                isBusy = false
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
                if (exported.savedToDownloads) {
                    appendLog("导出成功: ${exported.displayPath}")
                } else {
                    appendLog("导出失败，仍保留在应用目录")
                }
            } catch (e: Exception) {
                appendLog("导出失败: ${e.message}")
            } finally {
                isBusy = false
            }
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
}
