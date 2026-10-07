@echo off
setlocal EnableExtensions

chcp 65001 >nul
title Distributor-RAG Startup

set "ROOT_DIR=%~dp0"
set "VENV_DIR=%ROOT_DIR%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "PYTHON_CMD="

echo ========================================
echo   Distributor-RAG startup
echo ========================================
echo.

rem Prefer the Windows Python launcher, then fall back to python/python3 on PATH.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        python3 --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python3"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] 未找到可用的 Python 3。请先安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
    pause
    exit /b 1
)

for /f "tokens=2" %%V in ('%PYTHON_CMD% --version 2^>^&1') do set "PYTHON_VERSION=%%V"
echo [INFO] 检测到 Python %PYTHON_VERSION%（%PYTHON_CMD%）

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [ERROR] 当前 Python 版本低于 3.10，无法安装项目依赖。
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo [INFO] 正在创建虚拟环境：%VENV_DIR%
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] 创建 Python 虚拟环境失败。
        pause
        exit /b 1
    )
) else (
    echo [INFO] 已找到现有虚拟环境，跳过创建。
)

echo [INFO] 正在检查并安装后端依赖...
"%VENV_PYTHON%" -m pip install -r "%ROOT_DIR%backend\requirements.txt"
if errorlevel 1 (
    echo [ERROR] 后端依赖安装失败，请检查网络连接或 pip 配置。
    pause
    exit /b 1
)

echo [INFO] 正在启动后端：http://127.0.0.1:8000
start "Distributor-RAG Backend" /D "%ROOT_DIR%backend" cmd /k ""%VENV_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

where pnpm >nul 2>&1
if errorlevel 1 (
    echo [WARN] 未检测到 pnpm，已启动后端；前端未启动。
    echo [WARN] 安装 Node.js 和 pnpm 后，可再次运行此文件启动前端。
    exit /b 0
)

if not exist "%ROOT_DIR%frontend\node_modules" (
    echo [INFO] 正在安装前端依赖...
    pushd "%ROOT_DIR%frontend"
    call pnpm install
    if errorlevel 1 (
        popd
        echo [WARN] 前端依赖安装失败，已启动后端；前端未启动。
        pause
        exit /b 0
    )
    popd
)

echo [INFO] 正在启动前端：http://127.0.0.1:5173
start "Distributor-RAG Frontend" /D "%ROOT_DIR%frontend" cmd /k "pnpm run dev --host 127.0.0.1 --port 5173"

echo.
echo [OK] 后端和前端已启动。
echo [OK] 前端地址：http://127.0.0.1:5173
exit /b 0
