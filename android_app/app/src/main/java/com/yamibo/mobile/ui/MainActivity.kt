package com.yamibo.mobile.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
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
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
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
    val needsLegacyPermission = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q
    var legacyStorageGranted by remember {
        mutableStateOf(
            !needsLegacyPermission ||
                ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE
                ) == PackageManager.PERMISSION_GRANTED
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        legacyStorageGranted = granted
        vm.setLegacyStoragePermission(granted)
    }
    LaunchedEffect(needsLegacyPermission, legacyStorageGranted) {
        vm.setLegacyStoragePermission(!needsLegacyPermission || legacyStorageGranted)
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
                        }
                    )
                    LogCard(vm)
                }
            }
        }
    }
}

@Composable
private fun SessionCard(vm: MainViewModel) {
    SectionCard(title = "1) 登录与会话") {
        LabeledChips(
            label = "登录方式",
            options = AuthMode.entries,
            selected = vm.authMode,
            optionLabel = { it.label },
            onSelected = { vm.authMode = it }
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
                onValueChange = { vm.username = it },
                label = { Text("账号") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = vm.password,
                onValueChange = { vm.password = it },
                label = { Text("密码") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
        } else {
            OutlinedTextField(
                value = vm.cookie,
                onValueChange = { vm.cookie = it },
                label = { Text("Cookie") },
                modifier = Modifier.fillMaxWidth()
            )
        }

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
    SectionCard(title = "2) 搜索帖子") {
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
            onSelected = { vm.forumScope = it }
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
    SectionCard(title = "3) 目录候选与预览") {
        Button(
            onClick = vm::loadCatalogCandidates,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("提取目录候选")
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
    onRequestLegacyPermission: () -> Unit
) {
    SectionCard(title = "4) 抓取与导出") {
        OutlinedTextField(
            value = vm.outputTitle,
            onValueChange = { vm.outputTitle = it },
            label = { Text("输出标题（文件名）") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = vm.outputAuthor,
            onValueChange = { vm.outputAuthor = it },
            label = { Text("作者（可选）") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        EnumDropdown(
            label = "速度档位",
            selected = vm.speedMode,
            options = SpeedMode.entries,
            optionLabel = { it.label },
            onSelected = { vm.speedMode = it }
        )

        Text(
            "说明: 快速约 1 秒/章，仍带微弱随机抖动；为减少服务器压力请优先预览后再全量抓取。",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
        )

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
            onClick = vm::exportLatestToDownloads,
            enabled = !vm.isBusy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("一键导出到 Download")
        }

        if (vm.progressText.isNotBlank()) {
            Text(vm.progressText, color = MaterialTheme.colorScheme.primary)
        }
        if (vm.outputPath.isNotBlank()) {
            val tag = if (vm.outputSavedToDownloads) "Download" else "应用目录"
            Text("保存位置($tag): ${vm.outputPath}", fontSize = 12.sp)
        }
        Text(
            "提示: 若回退到应用目录，路径通常是 Android/data/com.yamibo.mobile/files/output。",
            fontSize = 12.sp
        )
    }
}

@Composable
private fun LogCard(vm: MainViewModel) {
    SectionCard(title = "5) 状态与日志") {
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
