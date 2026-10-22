$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$url = "http://127.0.0.1:8787/"
$healthUrl = "http://127.0.0.1:8787/api/health"

if (-not (Test-Path $python)) {
    throw "尚未安装依赖，请先运行 .\scripts\setup.ps1"
}

$running = $false
try {
    $null = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
    $running = $true
}
catch {
    $running = $false
}

if (-not $running) {
    $process = Start-Process `
        -FilePath $python `
        -ArgumentList "run.py" `
        -WorkingDirectory (Join-Path $root "backend") `
        -WindowStyle Hidden `
        -PassThru

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 400
        try {
            $null = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
            $ready = $true
            break
        }
        catch {}
    }

    if (-not $ready) {
        throw "后端启动失败，请确认 8787 端口未被其他程序占用"
    }
    Write-Host "羽球飞扬已启动，进程 PID: $($process.Id)"
}
else {
    Write-Host "羽球飞扬已在运行。"
}

Start-Process $url