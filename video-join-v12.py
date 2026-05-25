#!/usr/bin/env python3
"""
短剧视频拼接工具 v1.2.1
功能：
  - v1.0 拼接 + v1.1 尺寸强制
  - 自动检测硬件编码器（降低 CPU 占用）
  - 左上角剧名水印 + 右侧竖排"无不良引导"
"""

import os, re, subprocess, json, sys, time, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ====== 路径配置：读取 exe/脚本所在目录的 come/ 和 for/ ======
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
    """生成左上角剧名水印 PNG（纯文字，无背景）"""
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
    # 文字阴影（提升可读性）
    draw.text((pad+1, pad+1), text, font=font, fill=(0, 0, 0, 60))
    draw.text((pad, pad), text, font=font, fill=(255, 255, 255, 230))
    return img


def make_disclaimer_overlay():
    """生成右侧竖排免责声明 PNG（纯文字，无背景）"""
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
        # 阴影
        draw.text((pad+2, y+1), c, font=font, fill=(0, 0, 0, 60))
        draw.text((pad+1, y), c, font=font, fill=(255, 255, 255, 230))
        y += char_h + spacing
    return img


# ======================== 视频信息缓存 ========================

_cache_video_info = {}

def get_video_info(filepath):
    if filepath in _cache_video_info:
        return _cache_video_info[filepath]
    info = {'width': 0, 'height': 0, 'duration': 0}
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-show_entries', 'stream=width,height:format=duration',
             '-of', 'json', filepath],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(r.stdout)
        for s in data.get('streams', []):
            if s.get('width') and s.get('height'):
                info['width'] = s['width']
                info['height'] = s['height']
                break
        info['duration'] = float(data.get('format', {}).get('duration', 0))
    except Exception as e:
        print(f"  ⚠️ 无法读取: {Path(filepath).name} - {e}")
    _cache_video_info[filepath] = info
    return info

def get_duration(filepath):
    return get_video_info(filepath).get('duration', 0)

def get_target_size(w, h):
    return ALLOWED_SIZES['landscape'] if w > h else ALLOWED_SIZES['portrait']

# ======================== 边缘取色（仅用在宽高比不一致时） ========================

def detect_pad_color(video_path):
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        dur = get_duration(video_path)
        mid_time = dur / 2 if dur > 0 else 5
        subprocess.run(
            ['ffmpeg', '-ss', str(mid_time), '-i', video_path,
             '-vframes', '1', '-q:v', '2', '-y', tmp_path],
            capture_output=True, text=True, timeout=30
        )
        if not os.path.exists(tmp_path):
            return '#000000'
        img = Image.open(tmp_path)
        w, h = img.size
        strip_w = min(10, w // 4)
        def avg_color(pil_img):
            px = pil_img.load()
            tr, tg, tb, n = 0, 0, 0, 0
            for x in range(pil_img.width):
                for y in range(pil_img.height):
                    r, g, b = px[x, y][:3]
                    tr += r; tg += g; tb += b; n += 1
            return (tr//n, tg//n, tb//n)
        lc = avg_color(img.crop((0, 0, strip_w, h)))
        rc = avg_color(img.crop((w-strip_w, 0, w, h)))
        a = ((lc[0]+rc[0])//2, (lc[1]+rc[1])//2, (lc[2]+rc[2])//2)
        return f'#{a[0]:02x}{a[1]:02x}{a[2]:02x}'
    except:
        return '#000000'
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

# ======================== 编码器检测（硬件加速优先） ========================

_ENCODER_PARAMS = None

def get_encoder_params():
    """检测系统可用编码器，优先使用硬件加速以降低 CPU 占用"""
    global _ENCODER_PARAMS
    if _ENCODER_PARAMS is not None:
        return _ENCODER_PARAMS

    # 默认：快速软件编码
    name = "libx264 (software)"
    params = ['-c:v', 'libx264', '-b:v', '4000k', '-preset', 'ultrafast']

    try:
        r = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=10)
        encoders = r.stdout + r.stderr

        if sys.platform == 'darwin' and 'h264_videotoolbox' in encoders:
            name = "h264_videotoolbox (Apple Hardware)"
            params = ['-c:v', 'h264_videotoolbox', '-b:v', '4000k', '-quality', '90']
        elif sys.platform.startswith('win'):
            if 'h264_nvenc' in encoders:
                name = "h264_nvenc (NVIDIA)"
                params = ['-c:v', 'h264_nvenc', '-b:v', '4000k', '-preset', 'p7']
            elif 'h264_amf' in encoders:
                name = "h264_amf (AMD)"
                params = ['-c:v', 'h264_amf', '-b:v', '4000k', '-quality', 'speed']
            elif 'h264_qsv' in encoders:
                name = "h264_qsv (Intel QuickSync)"
                params = ['-c:v', 'h264_qsv', '-b:v', '4000k', '-preset', 'fast']
    except:
        pass

    print(f"  🎞 编码器: {name}")
    _ENCODER_PARAMS = params
    return params


# ======================== 拼接引擎（带水印） ========================

def build_overlay_filter(book_name, target_w, target_h):
    """
    构建完整 filter_complex 字符串：缩放(如需) + 水印叠加
    返回 (filter_string, overlay_pngs_paths)
    """
    # 生成水印 PNG
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
    """拼接 + 缩放 + 水印叠加（硬件编码）"""
    src_info  = [get_video_info(fp) for fp in file_list]
    max_w     = max(info['width'] for info in src_info)
    max_h     = max(info['height'] for info in src_info)
    target_w, target_h = get_target_size(max_w, max_h)

    # 是否需要缩放
    need_scale = not all(
        info['width'] == target_w and info['height'] == target_h
        for info in src_info
    )

    # 构建滤镜链
    need_pad = False
    pad_color = '#000000'
    if need_scale:
        src_ratio = max_w / max_h
        tgt_ratio = target_w / target_h
        need_pad = abs(src_ratio - tgt_ratio) > 0.001
        if need_pad:
            pad_color = detect_pad_color(file_list[0])

    tmp_list = output_path + '.fl.txt'
    with open(tmp_list, 'w', encoding='utf-8') as f:
        for fp in file_list:
            escaped = fp.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    # 构建 filter_complex
    if need_scale:
        if need_pad:
            scale = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
            pad   = f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
            filter_complex = f"[0:v]{scale},{pad}[vid];[vid][1:v]overlay=15:35[tmp];[tmp][2:v]overlay=W-overlay_w-15:(H-overlay_h)/2[out]"
        else:
            filter_complex = f"[0:v]scale={target_w}:{target_h}[vid];[vid][1:v]overlay=15:35[tmp];[tmp][2:v]overlay=W-overlay_w-15:(H-overlay_h)/2[out]"
    else:
        filter_complex = f"[0:v][1:v]overlay=15:35[tmp];[tmp][2:v]overlay=W-overlay_w-15:(H-overlay_h)/2[out]"

    try:
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', tmp_list,
            '-i', title_png,
            '-i', disc_png,
            '-filter_complex', filter_complex,
            '-map', '[out]', '-map', '0:a?',
            *get_encoder_params(),
            '-c:a', 'copy',
            '-pix_fmt', 'yuv420p',
            '-y', output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=7200)
        return True, target_w, target_h
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 失败: {e}")
        err = e.stderr[-500:] if e.stderr else ''
        print(f"     {err}")
        return False, None, None
    finally:
        if os.path.exists(tmp_list):
            os.remove(tmp_list)


# ======================== 核心逻辑 ========================

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
    need_scale = not all(
        get_video_info(fp)['width'] == target_w and get_video_info(fp)['height'] == target_h
        for _, fp in episodes
    )

    print(f"\n📁 《{book_name}》 共 {n} 集 (最大 {max_w}×{max_h} → {orient_name})")
    if need_scale:
        print(f"   缩放+边缘取色")
    print(f"   水印: 左上「《{book_name}」+ 右侧竖排「无不良引导」")

    # 预生成水印（每本书只生成一次）
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
        out_name = f"{book_name}-wys-{seq}.mp4"
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

    # 清理水印临时文件
    for p in [title_png, disc_png]:
        if os.path.exists(p):
            os.unlink(p)


# ======================== 主流程 ========================

def main():
    for cmd in ['ffmpeg', 'ffprobe']:
        try:
            subprocess.run([cmd, '-version'], capture_output=True, check=True)
        except:
            print(f"❌ 未找到 {cmd}，请确认 ffmpeg 已安装并加入系统 PATH")
            sys.exit(1)

    input_path = Path(INPUT_DIR)
    if not input_path.is_dir():
        print(f"❌ 输入目录不存在: {INPUT_DIR}")
        sys.exit(1)

    books = {}
    for f in os.listdir(INPUT_DIR):
        m = FILE_PATTERN.match(f)
        if m:
            book = m.group(1)
            ep  = int(m.group(2))
            books.setdefault(book, []).append((ep, str(input_path / f)))

    if not books:
        print("❌ 未找到匹配的 MP4 文件")
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
    print(f"   输出: {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
