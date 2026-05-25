@echo off
title 短剧视频拼接工具 v1.2.1
:: ============================================================
:: 短剧视频拼接工具 v1.2.1 — Windows 版
:: 依赖: python, ffmpeg
:: ============================================================

cd /d "%~dp0"
set "BASE_DIR=%CD%"
set "INPUT_DIR=%BASE_DIR%\come"
set "OUTPUT_DIR=%BASE_DIR%\for"

:: ─── 检测 Python ───
python --version >nul 2>&1
if errorlevel 1 (
    echo ==========================================
    echo   短剧视频拼接工具 v1.2.1
    echo ==========================================
    echo.
    echo [错误] 未检测到 Python
    echo 请从 https://www.python.org/downloads/ 安装
    echo.
    pause
    exit /b 1
)

:: ─── 检测 ffmpeg ───
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo ==========================================
    echo   短剧视频拼接工具 v1.2.1
    echo ==========================================
    echo.
    echo [错误] 未检测到 ffmpeg
    echo 请将 ffmpeg.exe 所在目录加入系统 PATH
    echo.
    pause
    exit /b 1
)

:: ─── 检测 Pillow ───
python -c "from PIL import Image" >nul 2>&1
if errorlevel 1 (
    echo 正在安装 Pillow 库...
    pip install Pillow -q
    if errorlevel 1 (
        echo [错误] Pillow 安装失败
        pause
        exit /b 1
    )
    echo Pillow 安装完成
)

:: ─── 检查 come 目录 ───
if not exist "%INPUT_DIR%" mkdir "%INPUT_DIR%"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

dir "%INPUT_DIR%\*.mp4" /a-d /b >nul 2>&1
if errorlevel 1 (
    echo ==========================================
    echo   短剧视频拼接工具 v1.2.1
    echo ==========================================
    echo.
    echo [提示] come 文件夹中没有 .mp4 文件
    echo 请将视频文件放入 come 目录后重新运行
    echo.
    pause
    exit /b 1
)

:: ─── 显示欢迎信息 ───
cls
echo ==========================================
echo     短剧视频拼接工具  v1.2.1
echo     Video Join Tool for Windows
echo ==========================================
echo.
echo 输入目录: %INPUT_DIR%
echo 输出目录: %OUTPUT_DIR%
echo.

:: 显示检测到的系列
echo [检测到的视频系列]
python -c "
import os, re
from pathlib import Path
input_dir = r'%INPUT_DIR%'
books = {}
for f in os.listdir(input_dir):
    m = re.match(r'^(.+)-第(\d+)集\.mp4$', f)
    if m:
        books.setdefault(m.group(1), []).append(int(m.group(2)))
for b in sorted(books.keys()):
    eps = sorted(books[b])
    print(f'  {b} - {len(eps)} 集 (第{eps[0]}-{eps[-1]}集)')
if not books:
    print('  (未识别到系列文件)')
"
echo.
echo ==========================================
echo 开始处理...
echo ==========================================
echo.

:: ─── 运行核心脚夲 ───
python "%BASE_DIR%\video-join-v12.py"
set "EXIT_CODE=%errorlevel%"

echo.
echo ==========================================
if %EXIT_CODE% equ 0 (
    echo 处理完成！
) else (
    echo 处理出错 (错误码: %EXIT_CODE%)
)
echo ==========================================

:: 显示输出文件
if exist "%OUTPUT_DIR%" (
    echo.
    echo [输出文件列表]
    dir "%OUTPUT_DIR%" /s /b /a-d 2>nul | findstr /i "\.mp4$" >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=*" %%i in ('dir "%OUTPUT_DIR%" /s /a-d /b 2^>nul ^| findstr /i "\.mp4$"') do (
            call :show_file "%%i"
        )
    ) else (
        echo   (无输出文件)
    )
)

echo.
pause
exit /b %EXIT_CODE%

:show_file
set "FPATH=%~1"
for %%i in ("%FPATH%") do set "FSIZE=%%~zi"
set /a MB=(FSIZE+1048575)/1048576
echo   ^> %MB% MB  %~n1
goto :eof
