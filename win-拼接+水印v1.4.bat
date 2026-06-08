@echo off
chcp 65001 >nul
cd /d "%~dp0"

:main
cls
echo ╔══════════════════════════════════════════════════╗
echo ║         短剧视频拼接工具  v1.4.0                  ║
echo ║         Video Join Tool for Windows               ║
echo ║         GPU 加速 + 自动降级                       ║
echo ╚══════════════════════════════════════════════════╝
echo.

REM ---- 检测 Python ----
echo 🔍 检测运行环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is required
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo   ✅ %%i

REM ---- 检测 ffmpeg ----
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo   ❌ 未找到 ffmpeg
    echo     请下载并将 ffmpeg.exe 放到本目录，或加入系统 PATH
    pause
    exit /b 1
) else (
    echo   ✅ ffmpeg: 已安装
)

REM ---- 检测 CUDA (GPU) ----
python -c "
import subprocess, sys
try:
    r = subprocess.run(['ffmpeg', '-hwaccels'], capture_output=True, text=True, timeout=10)
    has = 'cuda' in (r.stdout + r.stderr).lower()
    if has:
        r2 = subprocess.run(['ffmpeg', '-filters'], capture_output=True, text=True, timeout=10)
        filters = r2.stdout + r2.stderr
        has_filters = 'scale_cuda' in filters and 'overlay_cuda' in filters
        print(f'  ✅ CUDA: 可用 | scale_cuda/overlay_cuda: {\"可用\" if has_filters else \"不可用\"}')
    else:
        print('  ℹ️  CUDA: 不可用（使用CPU编码）')
except:
    print('  ℹ️  CUDA: 检测失败（使用CPU编码）')
"
echo.

REM ---- 检测 / 创建输入输出目录 ----
if not exist "come" mkdir come
if not exist "for" mkdir for

REM ---- 统计视频 ----
set COUNT=0
for %%i in (come\*.mp4) do set /a COUNT+=1
if %COUNT%==0 (
    echo   ❌ come 目录下没有 .mp4 文件
    echo     请把视频放到 come 文件夹后重新运行
    echo.
    pause
    exit /b 1
)
echo   📂 come\ 目录: %COUNT% 个 MP4 文件
echo.

REM ---- 显示本目录内容 ----
echo ══════════════════════════════════════════════════
echo.
if exist config.json (
    echo   ⚙️  配置: config.json (GPU 可开关)
    echo   ✏️  编辑: 运行 win-配置GPU加速v1.4.bat
) else (
    echo   ⚙️  配置文件首次运行自动生成
)
echo.
echo ══════════════════════════════════════════════════
echo.

echo 🚀 开始处理...
echo ──────────────────────────────────────────────────
echo.

python video-join-v12.py
set EXIT_CODE=%ERRORLEVEL%

echo.
echo ──────────────────────────────────────────────────
if %EXIT_CODE%==0 (
    echo ✅ 处理完成！
) else (
    echo ❌ 处理出错（错误码: %EXIT_CODE%）
)
echo   输出目录: %~dp0for\
echo.
echo   按任意键可查看输出文件列表...
pause >nul

echo.
echo 📦 输出文件：
dir /s /b "%~dp0for\*.mp4" 2>nul || echo   （无输出文件）
echo.
pause
