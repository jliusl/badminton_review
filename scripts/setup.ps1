$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $root ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $root ".uv-python"

Write-Host "[1/3] 安装本地 Python 3.12..."
uv python install 3.12

Write-Host "[2/3] 安装后端依赖..."
uv sync --project (Join-Path $root "backend")

Write-Host "[3/3] 安装前端依赖..."
Push-Location (Join-Path $root "frontend")
try {
    npm install
    npm run build
}
finally {
    Pop-Location
}

Write-Host "安装完成。运行 .\scripts\start.ps1 启动羽球飞扬。"