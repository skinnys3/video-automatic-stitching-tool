#!/bin/bash
# ============================================================
# 短剧视频拼接工具 v1.4.0 — macOS 版
# 功能：横版源同时输出横版+竖版，竖版源只输出竖版
#       GPU 加速 + 自动降级（仅 Windows NVIDIA）
# ============================================================

cd "$(dirname "$0")" || exit 1
BASE_DIR=$(pwd)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

print_banner() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo '╔══════════════════════════════════════════════════╗'
    echo '║         短剧视频拼接工具  v1.4.0                  ║'
    echo '║         Video Join Tool for macOS                ║'
    echo '║         GPU 加速 (仅 Windows)                    ║'
    echo '╚══════════════════════════════════════════════════╝'
    echo -e "${NC}"
}

check_status() {
    if [ $? -eq 0 ]; then echo -e "  ${GREEN}✅ $1${NC}"; else echo -e "  ${RED}❌ $1${NC}"; return 1; fi
}

print_banner
echo -e "${YELLOW}${BOLD}🔍 检测运行环境...${NC}"

PYTHON=""
if command -v python3 &>/dev/null; then PYTHON="python3"; elif command -v python &>/dev/null; then PYTHON="python"; else
    echo -e "  ${RED}❌ 未找到 Python3${NC}"; echo -e "  ${YELLOW}  请从 https://www.python.org/downloads/ 安装${NC}"; echo; read -p "按回车键退出..."; exit 1
fi
echo -e "  ${GREEN}✅ Python: $($PYTHON --version 2>&1)${NC}"

if command -v ffmpeg &>/dev/null; then echo -e "  ${GREEN}✅ ffmpeg: 已安装${NC}"; else
    echo -e "  ${RED}❌ 未找到 ffmpeg${NC}"; echo -e "  ${YELLOW}  请运行: brew install ffmpeg${NC}"; read -p "按回车键退出..."; exit 1
fi

echo -e "  ${YELLOW}📦 检查 Pillow 库...${NC}"
$PYTHON -c "from PIL import Image; print('ok')" 2>/dev/null
if [ $? -ne 0 ]; then echo -e "  ${YELLOW}  正在安装 Pillow...${NC}"; $PYTHON -m pip install Pillow -q; check_status "Pillow 安装完成"; fi

INPUT_DIR="$BASE_DIR/come"; OUTPUT_DIR="$BASE_DIR/for"
mkdir -p "$INPUT_DIR" "$OUTPUT_DIR"
echo; echo -e "${YELLOW}${BOLD}📂 目录信息${NC}"; echo -e "  输入: ${CYAN}$INPUT_DIR${NC}"; echo -e "  输出: ${CYAN}$OUTPUT_DIR${NC}"

count=$(ls "$INPUT_DIR"/*.mp4 2>/dev/null | wc -l)
if [ "$count" -eq 0 ]; then echo; echo -e "  ${RED}❌ come 目录下没有找到 .mp4 文件${NC}"; echo -e "  ${YELLOW}  请把视频放到 come/ 文件夹后重新运行${NC}"; echo; read -p "按回车键退出..."; exit 1; fi

echo; echo -e "${YELLOW}${BOLD}📋 检测到以下视频系列：${NC}"
ls "$INPUT_DIR"/*.mp4 2>/dev/null | sed -E 's/(.+)-第[0-9]+集\.mp4$/\1/' | sort -u | while read -r s; do
    cnt=$(ls "$INPUT_DIR/$s"*.mp4 2>/dev/null | wc -l | tr -d ' '); [ -n "$s" ] && echo -e "  ${CYAN}📺 ${s}${NC} — ${cnt} 集"
done

echo; echo -e "${GREEN}${BOLD}🚀 开始处理...${NC}"; echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo
$PYTHON "$BASE_DIR/video-join-v12.py"
EXIT_CODE=$?

echo; echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ $EXIT_CODE -eq 0 ]; then echo -e "${GREEN}${BOLD}✅ 处理完成！${NC}"; else echo -e "${RED}${BOLD}❌ 处理出错（错误码: $EXIT_CODE）${NC}"; fi
echo -e "  输出目录: ${CYAN}$OUTPUT_DIR${NC}"

echo; echo -e "${YELLOW}${BOLD}📦 输出文件：${NC}"
find "$OUTPUT_DIR" -name "*.mp4" -maxdepth 3 2>/dev/null | while read -r f; do
    size=$(du -h "$f" | cut -f1); echo -e "  ${GREEN}▶ $size${NC}  $(basename "$(dirname "$f")")/$(basename "$f")"
done

echo; read -p "按回车键退出..."
