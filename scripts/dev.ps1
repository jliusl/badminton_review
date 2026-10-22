$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "尚未安装依赖，请先运行 .\scripts\setup.ps1"
}

$backend = Start-Process `
    -FilePath $python `
    -ArgumentList "run.py" `
    -WorkingDirectory (Join-Path $root "backend") `
    -WindowStyle Hidden `
    -PassThru

Write-Host "后端 PID: $($backend.Id)，前端开发服务器即将启动。"
Push-Location (Join-Path $root "frontend")
try {
    npm run dev
}
finally {
    Pop-Location
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
}