param(
    [ValidateSet('check', 'install', 'upgrade', 'uninstall')]
    [string]$Mode = 'install',
    [switch]$DryRun,
    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$InstallDir = if ($env:JSA_INSTALL_DIR) { $env:JSA_INSTALL_DIR } else { Join-Path $env:USERPROFILE '.job-search-assistant' }
$ComposeFile = Join-Path $InstallDir 'docker-compose.release.yml'
$SourceDir = Join-Path $InstallDir 'source'
$ExtensionZip = Join-Path $InstallDir 'job-search-assistant-chrome-mv3.zip'
$RunnerScript = Join-Path $InstallDir 'automation-runner.py'
$RunnerPid = Join-Path $InstallDir 'automation-runner.pid'
$RunnerLog = Join-Path $InstallDir 'automation-runner.log'
$RunnerErrorLog = Join-Path $InstallDir 'automation-runner.error.log'
$SkillDir = Join-Path $env:USERPROFILE '.codex\skills\boss-zhipin-assistant'
$SetupUrl = 'http://127.0.0.1:8765/setup'

function Write-Step([string]$Message) { Write-Host $Message }
function Invoke-Step([scriptblock]$Action, [string]$Description) {
    if ($DryRun) { Write-Host "[dry-run] $Description"; return }
    & $Action
}
function Test-Command([string]$Name) { return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue) }
function Test-Port([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -eq $listener -or (Test-Path $ComposeFile)
}
function Test-Environment {
    $failures = 0
    Write-Step 'Job Search Assistant Windows 环境检查'
    if (Test-Command 'docker') { Write-Step '✓ Docker 命令已安装' } else { Write-Step '✗ 未安装 Docker Desktop'; $failures++ }
    if ((Test-Command 'docker') -and (& docker compose version 2>$null)) { Write-Step '✓ Docker Compose 可用' } else { Write-Step '✗ Docker Compose v2 不可用'; $failures++ }
    if (Test-Port 8765) { Write-Step '✓ 管理后台端口可用或由现有安装管理' } else { Write-Step '✗ 端口 8765 被占用'; $failures++ }
    if (Test-Port 8766) { Write-Step '✓ 向量服务端口可用或由现有安装管理' } else { Write-Step '✗ 端口 8766 被占用'; $failures++ }
    $chrome = Join-Path ${env:ProgramFiles} 'Google\Chrome\Application\chrome.exe'
    $chromeX86 = Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'
    if ((Test-Path $chrome) -or (Test-Path $chromeX86)) { Write-Step '✓ Chrome 已安装' } else { Write-Step '! 未检测到 Chrome' }
    return $failures
}
function Invoke-Compose([string[]]$Arguments) {
    & docker compose -f $ComposeFile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose 失败：$Arguments" }
}
function Prepare-Source {
    if ((Test-Path (Join-Path $RepoRoot 'docker-compose.release.yml')) -and (Test-Path (Join-Path $RepoRoot 'apps\extension'))) { return $RepoRoot }
    $archive = Join-Path $env:TEMP 'job-search-assistant-main.zip'
    Invoke-Step { Invoke-WebRequest 'https://github.com/a764506248/Job-Search-Assistant/archive/refs/heads/main.zip' -OutFile $archive } '下载源码归档'
    if ($DryRun) { return $SourceDir }
    if (Test-Path $SourceDir) { Remove-Item $SourceDir -Recurse -Force }
    Expand-Archive $archive -DestinationPath $InstallDir -Force
    $expanded = Get-ChildItem $InstallDir -Directory | Where-Object Name -Like 'Job-Search-Assistant-*' | Select-Object -First 1
    Move-Item $expanded.FullName $SourceDir
    Remove-Item $archive -Force
    return $SourceDir
}
function Wait-Service {
    if ($DryRun) { return }
    Write-Step '等待本地服务健康（最长 180 秒）…'
    foreach ($attempt in 1..90) {
        try { Invoke-RestMethod 'http://127.0.0.1:8765/v1/health' -TimeoutSec 2 | Out-Null; Write-Step '✓ 本地服务已就绪'; return } catch { Start-Sleep -Seconds 2 }
    }
    throw '本地服务未在 180 秒内就绪，请检查 Docker 日志。'
}

$failures = Test-Environment
if ($Mode -eq 'check') { exit $failures }
if ($Mode -eq 'uninstall') {
    if (Test-Path $RunnerPid) {
        $processId = Get-Content $RunnerPid -ErrorAction SilentlyContinue
        if ($processId -match '^\d+$' -and -not $DryRun) { Stop-Process -Id ([int]$processId) -ErrorAction SilentlyContinue }
    }
    if (Test-Path $ComposeFile) { Invoke-Step { Invoke-Compose @('down') } '停止 Docker 服务' }
    Invoke-Step { Remove-Item $ComposeFile, $ExtensionZip, $RunnerScript, $RunnerPid, $RunnerLog, $RunnerErrorLog -Force -ErrorAction SilentlyContinue } '移除安装器托管文件（保留 data）'
    Write-Step "用户数据保留在 $(Join-Path $InstallDir 'data')"
    exit 0
}
if ($failures -gt 0) { throw '请先解决环境检查中的阻塞项。' }

Invoke-Step { New-Item $InstallDir -ItemType Directory -Force | Out-Null } "创建 $InstallDir"
$resolvedSource = Prepare-Source
Invoke-Step { Copy-Item (Join-Path $resolvedSource 'docker-compose.release.yml') $ComposeFile -Force } '安装 Release Compose'
$sourceSkill = Join-Path $resolvedSource 'skills\boss-zhipin-assistant'
Invoke-Step {
    $profile = Join-Path $SkillDir 'user_profile.json'
    $saved = if (Test-Path $profile) { Get-Content $profile -Raw } else { $null }
    New-Item $SkillDir -ItemType Directory -Force | Out-Null
    Copy-Item "$sourceSkill\*" $SkillDir -Recurse -Force
    if ($saved) { Set-Content $profile $saved -Encoding UTF8 }
} '安装 BOSS Skill 并保留用户配置'
$extensionOutput = Join-Path $resolvedSource 'apps\extension\.output\chrome-mv3\*'
if (Test-Path $extensionOutput) {
    Invoke-Step { Compress-Archive $extensionOutput $ExtensionZip -Force } '打包统一 Chrome 扩展'
}
Invoke-Step { Copy-Item (Join-Path $resolvedSource 'scripts\automation-runner.py') $RunnerScript -Force } '安装宿主 automation runner'
Invoke-Step { Invoke-Compose @('pull') } '拉取三个服务镜像'
Invoke-Step { Invoke-Compose @('up', '-d') } '启动三个服务'
Wait-Service
if (Test-Command 'python') {
    Invoke-Step {
        $process = Start-Process python -ArgumentList @($RunnerScript) -RedirectStandardOutput $RunnerLog -RedirectStandardError $RunnerErrorLog -WindowStyle Hidden -PassThru
        Set-Content $RunnerPid $process.Id -Encoding ASCII
    } '启动宿主 automation runner'
} else { Write-Step '! 未检测到 Python，任务 API 可用，但宿主 runner 未启动' }
if (-not $NoOpen -and -not $DryRun) { Start-Process $SetupUrl }
Write-Step "安装完成：$SetupUrl"
