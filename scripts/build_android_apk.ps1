param(
    [switch]$Release
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$androidDir = Join-Path $repoRoot "android_app"

if (-not (Test-Path $androidDir)) {
    throw "未找到 android_app 目录: $androidDir"
}

$gradle = Get-Command gradle -ErrorAction SilentlyContinue
if (-not $gradle) {
    Write-Host "未检测到 gradle 命令。请先安装 Android Studio 或 Gradle，并确保 gradle 在 PATH 中。" -ForegroundColor Yellow
    exit 1
}

Push-Location $androidDir
try {
    if ($Release) {
        gradle assembleRelease
        $apk = Join-Path $androidDir "app\build\outputs\apk\release\app-release.apk"
    } else {
        gradle assembleDebug
        $apk = Join-Path $androidDir "app\build\outputs\apk\debug\app-debug.apk"
    }

    if (Test-Path $apk) {
        $releaseDir = Join-Path $repoRoot "release"
        if (-not (Test-Path $releaseDir)) {
            New-Item -ItemType Directory -Path $releaseDir | Out-Null
        }
        $target = Join-Path $releaseDir (Split-Path $apk -Leaf)
        Copy-Item -LiteralPath $apk -Destination $target -Force
        Write-Host "APK 已复制到: $target" -ForegroundColor Green
    } else {
        Write-Host "构建完成但未找到 APK: $apk" -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}
