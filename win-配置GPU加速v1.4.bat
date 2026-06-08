@echo off
chcp 65001 >nul
cd /d "%~dp0"

cls
echo ╔══════════════════════════════════════════════════╗
echo ║       GPU 加速配置工具  v1.4.0                    ║
echo ║       短剧视频拼接工具                            ║
echo ╚══════════════════════════════════════════════════╝
echo.

if not exist config.json (
    echo   ⚙️  配置文件不存在，正在创建默认配置...
    python -c "
import json
with open('config.json','w') as f:
    json.dump({'use_gpu': False}, f, ensure_ascii=False, indent=2)
print('  ✅ config.json 已创建')
" 2>nul
    if errorlevel 1 (
        echo   ❌ 创建失败，请检查 Python 是否可用
        pause
        exit /b 1
    )
)

REM 显示当前状态
python -c "
import json
try:
    with open('config.json') as f:
        cfg = json.load(f)
    val = cfg.get('use_gpu', False)
    print(f'  当前状态: GPU 加速 {\"开启 🟢\" if val else \"关闭 🔴\"}')
except:
    print('  ⚠️  无法读取配置文件')
" 2>nul

echo.
echo ══════════════════════════════════════════════════
echo.
echo  请选择操作：
echo    1. 开启 GPU 加速 🟢
echo    2. 关闭 GPU 加速 🔴
echo    3. 检测 CUDA 兼容性
echo    4. 用记事本编辑 config.json
echo    0. 退出
echo.
set /p CHOICE="  输入数字后按回车: "

if "%CHOICE%"=="1" (
    python -c "
import json
with open('config.json','w') as f:
    json.dump({'use_gpu': True}, f, ensure_ascii=False, indent=2)
print('  ✅ GPU 加速已开启 🟢')
print('')
print('  📌 注意:')
print('    需要 NVIDIA 显卡 + CUDA 版 ffmpeg')
print('    首次运行拼接时若 CUDA 失败，会自动降级为 CPU')
"
    echo.
    pause
    goto main
)

if "%CHOICE%"=="2" (
    python -c "
import json
with open('config.json','w') as f:
    json.dump({'use_gpu': False}, f, ensure_ascii=False, indent=2)
print('  ✅ GPU 加速已关闭 🔴')
"
    echo.
    pause
    goto main
)

if "%CHOICE%"=="3" (
    cls
    echo ══════════════════════════════════════════════════
    echo   CUDA 兼容性检测
    echo ══════════════════════════════════════════════════
    echo.

    echo  [1/3] 检测 ffmpeg -hwaccels...
    ffmpeg -hwaccels 2>&1 | findstr /i "cuda" >nul
    if errorlevel 1 (
        echo   ❌ 未检测到 CUDA 硬件加速
        echo     请安装 NVIDIA 官方驱动 + CUDA 版 ffmpeg
    ) else (
        echo   ✅ CUDA 硬件加速可用
    )
    echo.

    echo  [2/3] 检测 scale_cuda / overlay_cuda 滤镜...
    ffmpeg -filters 2>&1 | findstr "scale_cuda" >nul
    if errorlevel 1 (
        echo   ❌ scale_cuda 不可用
    ) else (
        echo   ✅ scale_cuda 可用
    )
    ffmpeg -filters 2>&1 | findstr "overlay_cuda" >nul
    if errorlevel 1 (
        echo   ❌ overlay_cuda 不可用
    ) else (
        echo   ✅ overlay_cuda 可用
    )
    echo.

    echo  [3/3] 检测 GPU 编码器...
    ffmpeg -encoders 2>&1 | findstr "nvenc" >nul
    if errorlevel 1 (
        echo   ❌ h264_nvenc 不可用（将使用 libx264）
    ) else (
        echo   ✅ h264_nvenc 可用
    )
    echo.

    echo ──────────────────────────────────────────────
    echo   CUDA 加速条件: 以上三项全部通过
    echo   只要有一个不通过，GPU 加速将自动降级为 CPU
    echo.
    pause
    goto main
)

if "%CHOICE%"=="4" (
    echo.
    echo   正在打开 config.json ...
    start notepad config.json
    echo.
    pause
    goto main
)

exit /b 0
