@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
:: 短剧视频拼接工具 v1.2 — Windows 版
:: ============================================================

:: 获取自身所在目录
set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"

:: ─── 颜色（使用 ANSI 转义，Win10+ 支持） ───
for /f %%i in ('echo prompt $E ^| cmd') do set "ESC=%%i"
set "RED=%ESC%[31m"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "CYAN=%ESC%[36m"
set "BOLD=%ESC%[1m"
set "NC=%ESC%[0m"

:: ─── 主流程 ───
cls
echo %BOLD%%CYAN%
echo ╔══════════════════════════════════════════════════╗
echo ║          短剧视频拼接工具  v1.2                  ║
echo ║         Video Join Tool for Windows               ║
echo ╚══════════════════════════════════════════════════╝
echo %NC%

:: 检测 Python
echo %YELLOW%%BOLD%🔍 检测运行环境...%NC%

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%  ❌ 未找到 Python%NC%
    echo %YELLOW%  请从 https://www.python.org/downloads/ 安装 Python%NC%
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PY_VER=%%i"
echo %GREEN%  ✅ Python: %PY_VER%%NC%

:: 检测 ffmpeg
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%  ⚠️ 未找到 ffmpeg%NC%
    echo %YELLOW%  请将 ffmpeg 添加到 PATH 环境变量%NC%
    echo.
    pause
    exit /b 1
)
echo %GREEN%  ✅ ffmpeg: 已安装%NC%

:: 检测 Pillow
echo %YELLOW%  📦 检查 Pillow 库...%NC%
python -c "from PIL import Image; print('ok')" 2>nul
if %errorlevel% neq 0 (
    echo %YELLOW%  正在安装 Pillow...%NC%
    pip install Pillow -q
    if %errorlevel% equ 0 (
        echo %GREEN%  ✅ Pillow 安装完成%NC%
    ) else (
        echo %RED%  ❌ Pillow 安装失败%NC%
        pause
        exit /b 1
    )
)

:: 检查目录
set "INPUT_DIR=%BASE_DIR%\come"
set "OUTPUT_DIR=%BASE_DIR%\for"

if not exist "%INPUT_DIR%" mkdir "%INPUT_DIR%"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo.
echo %YELLOW%%BOLD%📂 目录信息%NC%
echo   %CYAN%输入: %INPUT_DIR%%NC%
echo   %CYAN%输出: %OUTPUT_DIR%%NC%

:: 检测视频文件
set "count=0"
for %%i in ("%INPUT_DIR%\*.mp4") do set /a count+=1

if %count% equ 0 (
    echo.
    echo %RED%  ❌ come 目录下没有找到 .mp4 文件%NC%
    echo %YELLOW%  请把视频放到 come\ 文件夹后重新运行%NC%
    echo.
    pause
    exit /b 1
)

:: 检测系列
echo.
echo %YELLOW%%BOLD%📋 检测到的视频：%NC%
powershell -Command "
    Get-ChildItem '%INPUT_DIR%\*.mp4' | ForEach-Object {
        \$n = \$_.BaseName
        \$book = if (\$n -match '(.+)-第\d+集') { \$matches[1] } else { \$n }
        Write-Host ('  📺 ' + \$book + ' — ' + (Get-ChildItem ('$INPUT_DIR\' + \$book + '-第*.mp4') | Measure-Object).Count + ' 集')
    } | Get-Unique
"

echo.
echo %GREEN%%BOLD%🚀 开始处理...%NC%
echo %GREEN%%BOLD%━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%NC%
echo.

:: 运行核心脚本
python "%BASE_DIR%\video-join-v12.py"

set "EXIT_CODE=%errorlevel%"

echo.
echo %GREEN%%BOLD%━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%NC%
if %EXIT_CODE% equ 0 (
    echo %GREEN%%BOLD%✅ 处理完成！%NC%
) else (
    echo %RED%%BOLD%❌ 处理出错（错误码: %EXIT_CODE%）%NC%
)
echo   %CYAN%输出目录: %OUTPUT_DIR%%NC%

:: 显示输出文件
echo.
echo %YELLOW%%BOLD%📦 输出文件：%NC%
if exist "%OUTPUT_DIR%" (
    powershell -Command "
        Get-ChildItem '%OUTPUT_DIR%' -Recurse -Filter *.mp4 | ForEach-Object {
            \$mb = \$_.Length / 1MB
            Write-Host ('  ▶ {0:N1}MB  {1}' -f \$mb, \$_.FullName)
        }
    "
)

echo.
pause
