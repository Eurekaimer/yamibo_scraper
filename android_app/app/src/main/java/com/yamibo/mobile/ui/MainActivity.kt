package com.yamibo.mobile.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.viewmodel.compose.viewModel
import com.yamibo.mobile.data.AuthMode
import com.yamibo.mobile.data.ForumScope
import com.yamibo.mobile.data.SpeedMode

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            YamiboMobileApp()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun YamiboMobileApp(vm: MainViewModel = viewModel()) {
    val context = LocalContext.current
    val lifecycleOwner = androidx.lifecycle.compose.LocalLifecycleOwner.current

    val needsLegacyPermission = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q
    val needsNotifyPermission = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
    var notifyGranted by remember {
        mutableStateOf(
            !needsNotifyPermission ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.POST_NOTIFICATIONS
                ) == PackageManager.PERMISSION_GRANTED
        )
    }

    var legacyStorageGranted by remember {
        mutableStateOf(
            !needsLegacyPermission ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE
                ) == PackageManager.PERMISSION_GRANTED
        )
    }
    var overlayGranted by remember {
        mutableStateOf(
            Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)
        )
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        legacyStorageGranted = granted
        vm.setLegacyStoragePermission(granted)
    }
    val notifyPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        notifyGranted = granted
    }

    val requestOverlayPermission: () -> Unit = {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val intent = Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:${context.packageName}")
            )
            context.startActivity(intent)
        }
    }

    LaunchedEffect(needsLegacyPermission, legacyStorageGranted) {
        vm.setLegacyStoragePermission(!needsLegacyPermission || legacyStorageGranted)
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    overlayGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)
                    notifyGranted = !needsNotifyPermission ||
                        ContextCompat.checkSelfPermission(
                            context,
                            Manifest.permission.POST_NOTIFICATIONS
                        ) == PackageManager.PERMISSION_GRANTED
                }

                Lifecycle.Event.ON_STOP -> vm.persistNow()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            vm.persistNow()
        }
    }

    val scheme = lightColorScheme(
        primary = Color(0xFFB91C1C),
        onPrimary = Color.White,
        primaryContainer = Color(0xFFFEE2E2),
        onPrimaryContainer = Color(0xFF7F1D1D),
        secondary = Color(0xFFDC2626),
        background = Color(0xFFFFF5F5),
        surface = Color(0xFFFFFBFB),
        onSurface = Color(0xFF7F1D1D)
    )

    MaterialTheme(colorScheme = scheme) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text("Yamibo Scraper Mobile", fontWeight = FontWeight.Bold)
                            Text("手机端适配版", fontSize = 12.sp)
                        }
                    }
                )
            }
        ) { innerPadding ->
            Surface(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
            ) {
                val scroll = rememberScrollState()
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(scroll)
                        .padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    SessionCard(vm)
                    SearchCard(vm)
                    CatalogCard(vm)
                    CrawlCard(
                        vm = vm,
                        needLegacyPermission = needsLegacyPermission && !legacyStorageGranted,
                        onRequestLegacyPermission = {
                            permissionLauncher.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                        },
                        needNotifyPermission = needsNotifyPermission && !notifyGranted,
                        onRequestNotifyPermission = {
                            notifyPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        },
                        overlayGranted = overlayGranted,
                        onRequestOverlayPermission = requestOverlayPermission
                    )
                    SavedFilesCard(vm)
                    LogCard(vm)
                }
            }
        }
    }
}

@Composable
private fun SessionCard(vm: MainViewModel) {
    SectionCard(title = "登录与会话") {
        LabeledChips(
            label = "登录方式",
            options = AuthMode.entries,
            selected = vm.authMode,
            optionLabel = { it.label },
            onSelected = vm::updateAuthMode
        )

        OutlinedTextField(
            value = vm.userAgent,
            onValueChange = { vm.userAgent = it },
            label = { Text("User-Agent") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        if (vm.authMode == AuthMode.ACCOUNT) {
            OutlinedTextField(
                value = vm.username,
                onValueChange = {
                    vm.username = it
                    if (vm.rememberAuth) vm.persistNow()
                },
                label = { Text("账号") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = vm.password,
                onValueChange = {
                    vm.password = it
                    if (vm.rememberAuth) vm.persistNow()
                },
                label = { Text("密码") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Text(
                text = vm.loginStatusText,
                fontSize = 12.sp,
                color = if (vm.loginStatusOk) Color(0xFF166534) else MaterialTheme.colorScheme.primary
            )
        } else {
            OutlinedTextField(
                value = vm.cookie,
                onValueChange = {
                    vm.cookie = it
                    if (vm.rememberAuth) vm.persistNow()
                },
                label = { Text("Cookie") },
                modifier = Modifier.fillMaxWidth()
            )
            Text(
                text = vm.loginStatusText,
                fontSize = 12.sp,
                color = if (vm.loginStatusOk) Color(0xFF166534) else MaterialTheme.colorScheme.primary
            )
        }

        Text(
            text = "建议: 网络波动或频繁超时时，优先使用稳定代理再抓取，成功率和速度都会明显更好。",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
        )

        RowWithSwitch(
            label = "记住账号/密码/Cookie",
            checked = vm.rememberAuth,
            onCheckedChange = vm::updateRememberAuth
        )

        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = vm::doLogin,
                enabled = !vm.isBusy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("登录 / 重建会话")
            }
            OutlinedButton(
                onClick = vm::resetSession,
                enabled = !vm.isBusy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("重置")
            }
        }
    }
}

@Composable
private fun SearchCard(vm: MainViewModel) {
    SectionCard(title = "搜索帖子") {
        OutlinedTextField(
            value = vm.keyword,
            onValueChange = { vm.keyword = it },
            label = { Text("关键词") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        LabeledChips(
            label = "分区",
            options = ForumScope.entries,
            selected = vm.forumScope,
            optionLabel = { it.label },
            onSelected = vm::updateForumScope
        )

        Button(
            onClick = vm::searchThreads,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("搜索")
        }

        Text("搜索结果（按热度综合排序）", fontWeight = FontWeight.SemiBold)
        SelectableListBox(
            height = 220.dp,
            itemCount = vm.searchResults.size,
            selectedIndex = vm.selectedSearchIndex,
            onSelect = vm::chooseSearchResult,
            itemText = { idx ->
                val item = vm.searchResults[idx]
                "[${item.forumName}] ${item.title}\n回复:${item.replies} 浏览:${item.views} 热度:${item.popularityScore.toInt()}"
            }
        )
    }
}

@Composable
private fun CatalogCard(vm: MainViewModel) {
    SectionCard(title = "目录候选与预览") {
        Button(
            onClick = vm::loadCatalogCandidates,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("提取目录候选")
        }

        OutlinedTextField(
            value = vm.authorFilter,
            onValueChange = { vm.authorFilter = it },
            label = { Text("\u4f5c\u8005\u8fc7\u6ee4\uff08\u7559\u7a7a\u81ea\u52a8\u9996\u697c\u4f5c\u8005\uff09") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = vm.authorPageLimitText,
            onValueChange = { vm.authorPageLimitText = it.filter { ch -> ch.isDigit() }.take(3) },
            label = { Text("\u4f5c\u8005\u697c\u5c42\u626b\u63cf\u9875\u6570") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedButton(
            onClick = vm::loadAuthorChapters,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("\u6309\u4f5c\u8005\u697c\u5c42\u52a0\u8f7d")
        }


        Spacer(modifier = Modifier.height(4.dp))
        Text("目录候选（可手动选择）", fontWeight = FontWeight.SemiBold)
        SelectableListBox(
            height = 180.dp,
            itemCount = vm.catalogCandidates.size,
            selectedIndex = vm.selectedCandidateIndex,
            onSelect = vm::chooseCatalogCandidate,
            itemText = { idx ->
                val c = vm.catalogCandidates[idx]
                val sample = c.sampleTitles.joinToString(" / ")
                "${c.selector} | 章节:${c.chapterCount} | 评分:${"%.1f".format(c.score)}\n示例: $sample"
            }
        )

        OutlinedTextField(
            value = vm.previewCountText,
            onValueChange = { vm.previewCountText = it },
            label = { Text("预览章数") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Button(
            onClick = vm::previewChapters,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("预览")
        }

        if (vm.previewItems.isNotEmpty()) {
            Text("预览结果", fontWeight = FontWeight.SemiBold)
            SelectableListBox(
                height = 170.dp,
                itemCount = vm.previewItems.size,
                selectedIndex = -1,
                onSelect = {},
                itemText = { idx ->
                    val p = vm.previewItems[idx]
                    "${p.index + 1}. ${p.title}\n${p.snippet}..."
                }
            )

            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(
                    onClick = vm::confirmPreview,
                    enabled = !vm.isBusy,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("确认预览无误")
                }
                val confirmText = if (vm.previewConfirmed) "已确认" else "未确认"
                Text(confirmText)
            }
        }
    }
}

@Composable
private fun CrawlCard(
    vm: MainViewModel,
    needLegacyPermission: Boolean,
    onRequestLegacyPermission: () -> Unit,
    needNotifyPermission: Boolean,
    onRequestNotifyPermission: () -> Unit,
    overlayGranted: Boolean,
    onRequestOverlayPermission: () -> Unit
) {
    SectionCard(title = "抓取与导出") {
        Text(
            "推荐流程：先登录，再搜索帖子，选择目录候选并完成预览，最后开始抓取或导出。",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
        )
        OutlinedTextField(
            value = vm.outputTitle,
            onValueChange = {
                vm.outputTitle = it
                vm.persistNow()
            },
            label = { Text("输出标题（文件名）") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = vm.outputAuthor,
            onValueChange = {
                vm.outputAuthor = it
                vm.persistNow()
            },
            label = { Text("作者（可选）") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedButton(
            onClick = { vm.refreshSuggestedOutputMeta(forceReplace = true) },
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("按当前帖子重新推荐标题/作者")
        }

        EnumDropdown(
            label = "速度档位",
            selected = vm.speedMode,
            options = SpeedMode.entries,
            optionLabel = { it.label },
            onSelected = vm::updateSpeedMode
        )

        Text(
            "说明: 下载中可直接切换速度，新的档位会在下一章生效；失败回填也支持同样的动态切换。",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
        )

        if (needNotifyPermission) {
            Text(
                "建议允许通知权限，抓取切到后台时也能看到实时进度。",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary
            )
            OutlinedButton(
                onClick = onRequestNotifyPermission,
                enabled = !vm.isBusy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("授予通知权限")
            }
        } else {
            Text(
                "后台通知已可用，下载切后台仍可查看进度。",
                fontSize = 12.sp
            )
        }

        RowWithSwitch(
            label = "开启悬浮进度窗",
            checked = vm.enableOverlay,
            onCheckedChange = { enabled ->
                if (enabled && !overlayGranted) {
                    onRequestOverlayPermission()
                } else {
                    vm.setOverlayEnabled(enabled)
                }
            }
        )
        if (vm.enableOverlay && !overlayGranted) {
            Text(
                "悬浮窗权限未开启，当前仅显示通知栏进度。",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary
            )
        }

        if (needLegacyPermission) {
            Text(
                "当前设备是 Android 9 及以下，若要直接写入 Download 目录请先授权存储权限。",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary
            )
            OutlinedButton(
                onClick = onRequestLegacyPermission,
                enabled = !vm.isBusy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("授予存储权限（仅旧系统需要）")
            }
        } else {
            Text(
                "默认优先保存到 Download 目录；若系统限制，将自动回退到应用目录并可一键导出。",
                fontSize = 12.sp
            )
        }

        Button(
            onClick = vm::startCrawl,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (vm.isBusy) "执行中..." else "开始抓取（TXT）")
        }
        OutlinedButton(
            onClick = vm::retryFailedAndPatch,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("仅重试失败章节并回填")
        }
        OutlinedButton(
            onClick = vm::exportLatestToDownloads,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("一键导出到 Download")
        }
        OutlinedButton(
            onClick = vm::openLatestOutput,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("打开最新抓取文件")
        }

        if (vm.progressText.isNotBlank()) {
            Text(vm.progressText, color = MaterialTheme.colorScheme.primary)
        }
        if (vm.outputPath.isNotBlank()) {
            val tag = if (vm.outputSavedToDownloads) "Download" else "应用目录"
            Text("保存位置($tag): ${vm.outputPath}", fontSize = 12.sp)
        }
        if (vm.latestFailedCount > 0) {
            Text(
                "当前剩余失败章节: ${vm.latestFailedCount}（可点击“仅重试失败章节并回填”）",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary
            )
            if (vm.latestFailedTitles.isNotEmpty()) {
                SelectableListBox(
                    height = 120.dp,
                    itemCount = vm.latestFailedTitles.size,
                    selectedIndex = -1,
                    onSelect = {},
                    itemText = { idx -> "失败[${idx + 1}] ${vm.latestFailedTitles[idx]}" }
                )
            }
        }
        Text(
            "提示: 若回退到应用目录，路径通常是 Android/data/com.yamibo.mobile/files/output。",
            fontSize = 12.sp
        )
    }
}

@Composable
private fun LogCard(vm: MainViewModel) {
    SectionCard(title = "状态与日志") {
        Text("状态: ${vm.status}")
        OutlinedButton(
            onClick = vm::clearLogs,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
                Text("清空日志")
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(220.dp)
                .border(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.surface)
                .padding(6.dp)
        ) {
            if (vm.logs.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("暂无日志", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                }
            } else {
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    itemsIndexed(vm.logs) { _, line ->
                        Text(
                            text = line,
                            fontSize = 12.sp,
                            lineHeight = 18.sp,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SavedFilesCard(vm: MainViewModel) {
    SectionCard(title = "已抓取文件") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = vm::refreshSavedFiles,
                enabled = !vm.isBusy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("刷新文件列表")
            }
            OutlinedButton(
                onClick = vm::openSelectedFile,
                enabled = !vm.isBusy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("打开选中文件")
            }
            OutlinedButton(
                onClick = vm::convertSelectedTxtToEpub,
                enabled = !vm.isBusy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("将选中 TXT 转换为 EPUB（自动繁转简）")
            }
        }

        SelectableListBox(
            height = 180.dp,
            itemCount = vm.savedFiles.size,
            selectedIndex = vm.selectedSavedFileIndex,
            onSelect = vm::chooseSavedFile,
            itemText = { idx ->
                val f = vm.savedFiles[idx]
                val sizeKb = (f.sizeBytes / 1024.0).coerceAtLeast(0.1)
                "${f.name}\n${"%.1f".format(sizeKb)} KB"
            }
        )
        Text(
            "提示: 文件列表来自应用目录 output，可直接点击打开；TXT 转 EPUB 与正文抓取都会自动执行繁体转简体。",
            fontSize = 12.sp
        )
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            content = {
                Text(title, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                HorizontalDivider(color = MaterialTheme.colorScheme.primary.copy(alpha = 0.2f))
                content()
            }
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun <T> LabeledChips(
    label: String,
    options: List<T>,
    selected: T,
    optionLabel: (T) -> String,
    onSelected: (T) -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, fontWeight = FontWeight.SemiBold)
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            options.forEach { option ->
                FilterChip(
                    selected = option == selected,
                    onClick = { onSelected(option) },
                    label = { Text(optionLabel(option)) }
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> EnumDropdown(
    label: String,
    selected: T,
    options: List<T>,
    optionLabel: (T) -> String,
    onSelected: (T) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }

    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = !expanded }
    ) {
        OutlinedTextField(
            value = optionLabel(selected),
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor()
        )
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { item ->
                DropdownMenuItem(
                    text = { Text(optionLabel(item)) },
                    onClick = {
                        onSelected(item)
                        expanded = false
                    }
                )
            }
        }
    }
}

@Composable
private fun RowWithSwitch(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    enabled: Boolean = true
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = label,
            modifier = Modifier.weight(1f)
        )
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            enabled = enabled
        )
    }
}

@Composable
private fun SelectableListBox(
    height: androidx.compose.ui.unit.Dp,
    itemCount: Int,
    selectedIndex: Int,
    onSelect: (Int) -> Unit,
    itemText: (Int) -> String
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(height)
            .border(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(4.dp)
    ) {
        if (itemCount <= 0) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("暂无内容", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
            }
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                itemsIndexed((0 until itemCount).toList()) { _, idx ->
                    val selected = idx == selectedIndex
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(
                                if (selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.10f)
                                else Color.Transparent,
                                RoundedCornerShape(8.dp)
                            )
                            .clickable { onSelect(idx) }
                            .padding(horizontal = 8.dp, vertical = 6.dp)
                    ) {
                        Text(
                            text = itemText(idx),
                            fontSize = 12.sp,
                            lineHeight = 18.sp
                        )
                    }
                }
            }
        }
    }
}
