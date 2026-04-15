package com.yamibo.mobile.data

const val BASE_URL = "https://bbs.yamibo.com/"

enum class AuthMode(val label: String) {
    ACCOUNT("账号密码"),
    COOKIE("Cookie")
}

enum class ForumScope(val label: String, val ids: List<Int>) {
    TRANSLATION("译文区(55)", listOf(55)),
    LITERATURE("文学区(49)", listOf(49)),
    BOTH("双区(49+55)", listOf(49, 55))
}

enum class SpeedMode(
    val label: String,
    val delayMinMs: Long,
    val delayMaxMs: Long,
    val maxConcurrency: Int
) {
    TURBO("极速", 80L, 220L, 3),
    FAST("快速", 280L, 680L, 2),
    BALANCED("平衡", 900L, 1600L, 1),
    GENTLE("稳妥", 1800L, 3200L, 1)
}

data class SearchResult(
    val title: String,
    val url: String,
    val forumId: Int?,
    val forumName: String,
    val replies: Int,
    val views: Int,
    val replyRank: Int,
    val viewRank: Int,
    val popularityScore: Double
)

data class Chapter(
    val title: String,
    val url: String,
    val pid: String,
    var content: String = ""
)

data class CatalogScoreDetail(
    val base: Double,
    val pidBonus: Double,
    val titleBonus: Double,
    val structureBonus: Double,
    val sizeBonus: Double,
    val qualityPenalty: Double,
    val pidCount: Int,
    val probableTitleCount: Int,
    val suspiciousTitleCount: Int
)

data class CatalogCandidate(
    val selector: String,
    val chapters: List<Chapter>,
    val chapterCount: Int,
    val score: Double,
    val scoreDetail: CatalogScoreDetail,
    val sampleTitles: List<String>
)

data class PreviewItem(
    val index: Int,
    val title: String,
    val snippet: String
)

data class CrawlProgress(
    val done: Int,
    val total: Int,
    val currentTitle: String,
    val etaSeconds: Long
)

data class CrawlResult(
    val txtPath: String,
    val displayPath: String,
    val fileName: String,
    val savedToDownloads: Boolean,
    val localWorkingPath: String,
    val failedRecordsPath: String?,
    val localFallbackPath: String?,
    val chapterCount: Int,
    val failedCount: Int,
    val failedTitles: List<String>
)

data class ExportResult(
    val savedToDownloads: Boolean,
    val displayPath: String,
    val absolutePath: String,
    val localFallbackPath: String?
)

data class SavedOutputFile(
    val name: String,
    val absolutePath: String,
    val modifiedAt: Long,
    val sizeBytes: Long
)

data class FailedChapterRecord(
    val index: Int,
    val title: String,
    val url: String,
    val marker: String
)

data class RetryFillResult(
    val total: Int,
    val succeeded: Int,
    val remaining: Int,
    val localWorkingPath: String,
    val failedRecordsPath: String?,
    val remainingTitles: List<String>
)
