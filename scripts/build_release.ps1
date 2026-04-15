param(
  [string]$AppName = "YamiboScraperGUI"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = ".\.venv\Scripts\python.exe"
$pyinstaller = ".\.venv\Scripts\pyinstaller.exe"

if (!(Test-Path $python)) { throw "Python not found: $python" }
if (!(Test-Path $pyinstaller)) { throw "PyInstaller not found: $pyinstaller" }

Write-Host "==> Syntax check"
& $python -m py_compile gui_app.py yamibo_scraper.py cli.py search.py config_store.py

Write-Host "==> Build onefile exe (with assets)"
$piArgs = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--windowed",
  "--name", $AppName,
  "--add-data", "assets;assets",
  "gui_app.py"
)
& $pyinstaller @piArgs

$releaseDir = Join-Path $root "release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$exePath = Join-Path $root ("dist\" + $AppName + ".exe")
if (!(Test-Path $exePath)) { throw "Build failed, exe not found: $exePath" }

$targetExe = Join-Path $releaseDir ($AppName + ".exe")
Copy-Item -Force $exePath $targetExe

$zipPath = Join-Path $releaseDir ($AppName + "-win64.zip")
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path $targetExe -DestinationPath $zipPath

Write-Host ""
Write-Host "Build completed:"
Write-Host ("EXE: " + $targetExe)
Write-Host ("ZIP: " + $zipPath)

