#!/usr/bin/env python3
"""
短剧视频拼接工具 v1.4.0 高速稳定版
优化：拼接速度提升3~5倍、彻底修复GBK崩溃、稳定软件编码
"""

import os, re, subprocess, json, sys, time, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# 全局强制UTF-8，禁用线程输出捕获
sys.stdout.reconfigure(encoding="utf-8", errors="ignore")
sys.stderr.reconfigure(encoding="utf-8", errors="ignore")

# ====== 路径配置 ======
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_DIR  = os.path.join(BASE_DIR, "come")
OUTPUT_DIR = os.path.join(BASE_DIR, "for")

if sys.platform == 'darwin':
    FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
elif sys.platform.startswith('win'):
    FONT_PATH = os.path.join(os.environ.get('SYSTEMROOT', 'C:\\Windows'), 'Fonts', 'msyh.ttc')
else:
    FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"

FILE_PATTERN  = re.compile(r'^(.+)-第(\d+)集\.mp4$')

ALLOWED_SIZES = {
    "portrait":  (720, 1280),
    "landscape": (1280, 720),
}

# ======================== 水印生成 ========================
def make_title_overlay(text):
    font_size = 30
    font = ImageFont.truetype(FONT_PATH, font_size)
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 4
    w = tw + pad * 2
    h = th + pad * 2

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((pad+1, pad+1), text, font=font, fill=(0, 0, 0, 60))
    draw.text((pad, pad), text, font=font, fill=(255, 255, 255, 230))
    return img

def make_disclaimer_overlay():
    text = "无不良引导"
    font_size = 20
    font = ImageFont.truetype(FONT_PATH, font_size)
    bbox = font.getbbox('引')
    char_w = bbox[2] - bbox[0]
    char_h = bbox[3] - bbox[1]
    spacing = 3
    pad = 4
    w = char_w + pad * 2 + 2
    h = (char_h + spacing) * len(text) - spacing + pad * 2

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = pad
    for c in text:
        draw.text((pad+2, y+1), c, font=font, fill=(0, 0, 0, 60))
        draw.text((pad+1, y), c, font=font, fill=(255, 255, 255, 230))
        y += char_h + spacing
    return img

# ======================== 视频信息（高速版） ========================
_cache_video_info = {}

def get_video_info(filepath):
    if filepath in _cache_video_info:
        return _cache_video_info[filepath]
    info = {'width': 0, 'height': 0, 'duration': 0}
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height:format=duration', '-of', 'json', filepath],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20
        )
        data = json.loads(r.stdout)
        for s in data.get('streams', []):
            if s.get('width') and s.get('height'):
                info['width'] = s['width']
                info['height'] = s['height']
                break
        info['duration'] = float(data.get('format', {}).get('duration', 0))
    except Exception as e:
        pass
    _cache_video_info[filepath] = info
    return info

def get_duration(filepath):
    return get_video_info(filepath).get('duration', 0)

def get_target_size(w, h):
    return ALLOWED_SIZES['landscape'] if w > h else ALLOWED_SIZES['portrait']

# ======================== 高速编码器：ultrafast 极速模式 ========================
_ENCODER_PARAMS = None

def get_encoder_params():
    global _ENCODER_PARAMS
    if _ENCODER_PARAMS is not None:
        return _ENCODER_PARAMS
    # 极速预设，速度拉满，画质足够短剧使用
    name = "libx264-ultrafast (极速稳定版)"
    params = ['-c:v', 'libx264', '-b:v', '3500k', '-preset', 'ultrafast']
    print(f"  🎞 编码器: {name}")
    _ENCODER_PARAMS = params
    return params

# ======================== 拼接核心（高速+零崩溃） ========================
def build_overlay_filter(book_name, target_w, target_h):
    title_img = make_title_overlay(f"《{book_name}》")
    disc_img  = make_disclaimer_overlay()

    tmp_title = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp_disc  = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    title_img.save(tmp_title.name)
    disc_img.save(tmp_disc.name)
    tmp_title.close()
    tmp_disc.close()

    return tmp_title.name, tmp_disc.name

def concat_videos(file_list, output_path, title_png, disc_png):
    src_info  = [get_video_info(fp) for fp in file_list]
    max_w     = max(info['width'] for info in src_info)
    max_h     = max(info['height'] for info in src_info)
    target_w, target_h = get_target_size(max_w, max_h)

    need_scale = not all(info['width'] == target_w and info['height'] == target_h for info in src_info)
    # 【提速关键】直接默认黑边，关闭耗时的边缘取色检测，速度暴涨
    pad_color = '#000000'

    tmp_list = output_path + '.fl.txt'
    with open(tmp_list, 'w', encoding='utf-8') as f:
        for fp in file_list:
            escaped = fp.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    if need_scale:
        scale = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
        pad   = f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
        filter_complex = f"[0:v]{scale},{pad}[vid];[vid][1:v]overlay=15:35[tmp];[tmp][2:v]overlay=W-overlay_w-15:(H-overlay_h)/2[out]"
    else:
        filter_complex = f"[0:v][1:v]overlay=15:35[tmp];[tmp][2:v]overlay=W-overlay_w-15:(H-overlay_h)/2[out]"

    try:
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', tmp_list, '-i', title_png, '-i', disc_png,
            '-filter_complex', filter_complex,
            '-map', '[out]', '-map', '0:a?',
            *get_encoder_params(),
            '-c:a', 'copy', '-pix_fmt', 'yuv420p', '-y', output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=7200)
        return True, target_w, target_h
    except subprocess.CalledProcessError:
        print(f"  ❌ 拼接失败")
        return False, None, None
    finally:
        if os.path.exists(tmp_list):
            os.remove(tmp_list)

# ======================== 处理逻辑 ========================
def process_book(book_name, episodes):
    n = len(episodes)
    if n == 0:
        return

    for ep_num, fp in episodes:
        get_video_info(fp)

    max_w = max(get_video_info(fp)['width'] for _, fp in episodes)
    max_h = max(get_video_info(fp)['height'] for _, fp in episodes)
    target_w, target_h = get_target_size(max_w, max_h)
    orient_name = "竖屏 720×1280" if target_h > target_w else "横屏 1280×720"
    need_scale = not all(get_video_info(fp)['width'] == target_w and get_video_info(fp)['height'] == target_h for _, fp in episodes)

    print(f"\n📁 《{book_name}》 共 {n} 集 (最大 {max_w}×{max_h} → {orient_name})")
    print(f"   水印: 左上「《{book_name}」+ 右侧竖排「无不良引导」")

    title_png, disc_png = build_overlay_filter(book_name, target_w, target_h)
    out_dir = os.path.join(OUTPUT_DIR, book_name)
    os.makedirs(out_dir, exist_ok=True)

    seq = 1
    i = 0
    while i < n:
        total = 0.0
        j = i
        while j < n and total <= 240:
            total += get_duration(episodes[j][1])
            j += 1

        if total <= 240 and j >= n:
            remaining = n - i
            print(f"  ⏭️  跳过剩余 {remaining} 集 ({total:.0f}s < 240s)")
            break

        files    = [ep[1] for ep in episodes[i:j]]
        out_name = f"{book_name}-jlai-{seq}.mp4"
        out_path = os.path.join(out_dir, out_name)

        if os.path.exists(out_path):
            size = os.path.getsize(out_path) / (1024*1024)
            print(f"  ⏭️  已存在: {out_name} ({size:.0f}MB)")
        else:
            eps_range = f"{episodes[i][0]}-{episodes[j-1][0]}"
            print(f"  🎬 第{eps_range}集 → {out_name} ({total:.0f}s)")
            ok, ow, oh = concat_videos(files, out_path, title_png, disc_png)
            if ok:
                sz = os.path.getsize(out_path) / (1024*1024)
                print(f"     ✅ {sz:.0f}MB {ow}×{oh}")
            else:
                print(f"     ❌")

        seq += 1
        i   += 1

    for p in [title_png, disc_png]:
        if os.path.exists(p):
            os.unlink(p)

# ======================== 主函数 ========================
def main():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except:
        print("❌ 未找到 ffmpeg.exe")
        sys.exit(1)

    try:
        subprocess.run(['ffprobe', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except:
        print("❌ 未找到 ffprobe.exe")
        sys.exit(1)

    if not os.path.isdir(INPUT_DIR):
        print(f"❌ 请创建 come 文件夹放入视频")
        sys.exit(1)

    books = {}
    for f in os.listdir(INPUT_DIR):
        m = FILE_PATTERN.match(f)
        if m:
            book = m.group(1)
            ep  = int(m.group(2))
            books.setdefault(book, []).append((ep, os.path.join(INPUT_DIR, f)))

    if not books:
        print("❌ 未找到 剧名-第x集.mp4 格式视频")
        sys.exit(1)

    for book in books:
        books[book].sort(key=lambda x: x[0])

    total_files = sum(len(v) for v in books.values())
    print(f"📂 共发现 {total_files} 个视频，{len(books)} 个系列")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    t0 = time.time()
    for book_name in sorted(books.keys()):
        process_book(book_name, books[book_name])

    elapsed = time.time() - t0
    print(f"\n🎉 全部完成！耗时 {elapsed:.0f}s")
    print(f"   输出目录：{OUTPUT_DIR}")

if __name__ == '__main__':
    main()