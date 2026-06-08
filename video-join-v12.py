#!/usr/bin/env python3
"""
短剧视频拼接工具 v1.4.0
功能：
  - 横版源同时输出横版+竖版，竖版源只输出竖版
  - 横转竖用纯黑填充
  - 横转竖时书名居中在顶部黑色填充区
  - 书名自动缩小字体，始终在一行内完整显示
  - 自适应文件夹命名：书名-横版 / 书名-竖版
  - 输出命名：书名-ai-横/竖-日期-序号
  - 自动检测硬件编码器（降低 CPU 占用）
  - 左上角剧名水印 + 右侧竖排"无不良引导"
  - macOS 自动嵌入首帧封面（修复 Finder 预览黑色）
"""

import os, re, subprocess, json, sys, time, tempfile
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ====== GPU 配置 ======
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
_USE_GPU = None  # None = 未加载, True/False 从 config 读取

def get_config():
    """读取/创建配置文件"""
    global _USE_GPU
    if _USE_GPU is not None:
        return _USE_GPU
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            _USE_GPU = cfg.get('use_gpu', False)
        except:
            _USE_GPU = False
    else:
        # 自动检测: Windows + NVIDIA CUDA
        has_cuda = False
        if sys.platform.startswith('win'):
            try:
                r = subprocess.run(['ffmpeg', '-hwaccels'], capture_output=True, text=True, errors='replace', timeout=10)
                has_cuda = 'cuda' in (r.stdout + r.stderr).lower()
            except:
                pass
        _USE_GPU = has_cuda
        # 写入默认配置
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump({"use_gpu": _USE_GPU}, f, ensure_ascii=False, indent=2)
            print(f"  ⚙️ 已生成配置文件: {CONFIG_PATH}")
        except:
            pass
    print(f"  ⚙️ GPU 加速: {'开启' if _USE_GPU else '关闭'}")
    return _USE_GPU

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

PORTRAIT_SIZE  = (720, 1280)
LANDSCAPE_SIZE = (1280, 720)

# ======================== 水印生成 ========================

def make_title_overlay(text, max_width=680):
    """生成剧名水印 PNG，自动缩小字体以保持在一行内"""
    font = None
    for font_size in range(30, 7, -1):
        try:
            f = ImageFont.truetype(FONT_PATH, font_size)
            if f.getbbox(text)[2] - f.getbbox(text)[0] <= max_width:
                font = f
                break
        except:
            continue
    if font is None:
        font = ImageFont.truetype(FONT_PATH, 10)

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
            capture_output=True, text=True, errors='replace', timeout=30
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

# ======================== 边缘取色 ========================

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
            capture_output=True, text=True, errors='replace', timeout=30
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
_USE_CUDA_FILTERS = None  # scale_cuda/overlay_cuda 是否可用

def get_encoder_params():
    global _ENCODER_PARAMS
    if _ENCODER_PARAMS is not None:
        return _ENCODER_PARAMS

    name = "libx264 (software)"
    params = ['-c:v', 'libx264', '-b:v', '4000k', '-preset', 'ultrafast']

    try:
        r = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, errors='replace', timeout=10)
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


def check_cuda_filters():
    """检测 CUDA filter (scale_cuda, overlay_cuda) 是否可用"""
    global _USE_CUDA_FILTERS
    if _USE_CUDA_FILTERS is not None:
        return _USE_CUDA_FILTERS
    _USE_CUDA_FILTERS = False
    try:
        r = subprocess.run(['ffmpeg', '-filters'], capture_output=True, text=True, errors='replace', timeout=10)
        filters = r.stdout + r.stderr
        if 'scale_cuda' in filters and 'overlay_cuda' in filters:
            _USE_CUDA_FILTERS = True
    except:
        pass
    return _USE_CUDA_FILTERS


# ======================== 水印临时文件构建 ========================

def build_overlay_filter(book_name, max_width=680):
    """生成水印 PNG，返回 (title_png_path, disc_png_path)"""
    title_img = make_title_overlay(f"《{book_name}》", max_width)
    disc_img  = make_disclaimer_overlay()

    tmp_title = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp_disc  = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    title_img.save(tmp_title.name)
    disc_img.save(tmp_disc.name)
    tmp_title.close()
    tmp_disc.close()

    return tmp_title.name, tmp_disc.name


# ======================== 拼接引擎 ========================

def concat_videos(file_list, output_path, title_png, disc_png, target_w, target_h):
    """拼接 + 缩放到 target_w×target_h + 水印叠加"""
    src_info  = [get_video_info(fp) for fp in file_list]
    max_w     = max(info['width'] for info in src_info)
    max_h     = max(info['height'] for info in src_info)

    # 是否需要缩放
    need_scale = not all(
        info['width'] == target_w and info['height'] == target_h
        for info in src_info
    )

    # 是否需要填充黑边（统一用黑色）
    need_pad = False
    pad_color = '#000000'
    if need_scale:
        src_ratio = max_w / max_h
        tgt_ratio = target_w / target_h
        need_pad = abs(src_ratio - tgt_ratio) > 0.001

    # 确定书名水印位置（横转竖：顶部黑色填充区居中；其余：左上角）
    is_landscape_to_portrait = max_w > max_h and target_h > target_w
    if is_landscape_to_portrait:
        title_overlay = "overlay=(W-overlay_w)/2:240"
    else:
        title_overlay = "overlay=15:35"
    disc_overlay = "overlay=W-overlay_w-15:(H-overlay_h)/2"

    tmp_list = output_path + '.fl.txt'
    with open(tmp_list, 'w', encoding='utf-8') as f:
        for fp in file_list:
            escaped = fp.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    # ---- 判断是否用 CUDA 加速 ----
    use_cuda = (get_config() and sys.platform.startswith('win')
                and check_cuda_filters() and need_scale)

    # 构建 filter_complex：统一顺序 缩放填充 → 书名水印 → 免责声明
    if use_cuda:
        # CUDA 路径：scale_cuda (GPU) → hwdownload → pad/overlay (CPU) → NVENC (GPU)
        scale_part = (f"hwupload_cuda,scale_cuda={target_w}:{target_h}:"
                      f"force_original_aspect_ratio=decrease,hwdownload,format=nv12")
        if need_pad:
            pad_str = f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
            fc = (f"[0:v]{scale_part},{pad_str}[vid];"
                  f"[vid][1:v]{title_overlay}[tmp];"
                  f"[tmp][2:v]{disc_overlay}[out]")
        else:
            fc = (f"[0:v]{scale_part}[vid];"
                  f"[vid][1:v]{title_overlay}[tmp];"
                  f"[tmp][2:v]{disc_overlay}[out]")
    else:
        # CPU 路径：scale + pad + overlay (全部 CPU)
        scale_str = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
        pad_str   = f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
        if need_scale:
            if need_pad:
                fc = f"[0:v]{scale_str},{pad_str}[vid];[vid][1:v]{title_overlay}[tmp];[tmp][2:v]{disc_overlay}[out]"
            else:
                fc = f"[0:v]{scale_str}[vid];[vid][1:v]{title_overlay}[tmp];[tmp][2:v]{disc_overlay}[out]"
        else:
            fc = f"[0:v][1:v]{title_overlay}[tmp];[tmp][2:v]{disc_overlay}[out]"

    filter_complex = fc

    try:
        cmd = ['ffmpeg']
        if use_cuda:
            cmd += ['-hwaccel', 'cuda']  # 启用 GPU 解码
        cmd += [
            '-f', 'concat', '-safe', '0',
            '-i', tmp_list,
            '-i', title_png,
            '-i', disc_png,
            '-filter_complex', filter_complex,
            '-map', '[out]', '-map', '0:a?',
        ]
        cmd += get_encoder_params()
        cmd += ['-c:a', 'copy', '-pix_fmt', 'yuv420p', '-y', output_path]
        subprocess.run(cmd, check=True, capture_output=True, text=True, errors='replace', timeout=7200)
        return True, target_w, target_h
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 失败: {e}")
        err = e.stderr[-500:] if e.stderr else ''
        print(f"     {err}")
        # CUDA 失败时自动降级为 CPU 重试一次
        if use_cuda:
            print(f"     → CUDA 失败, 降级到 CPU 重试...")
            return concat_videos_cpu_fallback(
                file_list, output_path, title_png, disc_png,
                target_w, target_h, need_scale, need_pad,
                max_w, max_h, is_landscape_to_portrait
            )
        return False, None, None
    finally:
        if os.path.exists(tmp_list):
            os.remove(tmp_list)


def concat_videos_cpu_fallback(file_list, output_path, title_png, disc_png,
                                target_w, target_h, need_scale, need_pad,
                                max_w, max_h, is_landscape_to_portrait):
    """CUDA 降级后的 CPU 重试——纯 CPU filter，不加 -hwaccel"""
    if is_landscape_to_portrait:
        title_overlay = "overlay=(W-overlay_w)/2:240"
    else:
        title_overlay = "overlay=15:35"
    disc_overlay = "overlay=W-overlay_w-15:(H-overlay_h)/2"
    pad_color = '#000000'

    tmp_list = output_path + '.fl.txt'
    with open(tmp_list, 'w', encoding='utf-8') as f:
        for fp in file_list:
            escaped = fp.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    scale_str = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease"
    pad_str   = f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
    if need_scale:
        if need_pad:
            fc = f"[0:v]{scale_str},{pad_str}[vid];[vid][1:v]{title_overlay}[tmp];[tmp][2:v]{disc_overlay}[out]"
        else:
            fc = f"[0:v]{scale_str}[vid];[vid][1:v]{title_overlay}[tmp];[tmp][2:v]{disc_overlay}[out]"
    else:
        fc = f"[0:v][1:v]{title_overlay}[tmp];[tmp][2:v]{disc_overlay}[out]"

    try:
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', tmp_list,
            '-i', title_png,
            '-i', disc_png,
            '-filter_complex', fc,
            '-map', '[out]', '-map', '0:a?',
            '-c:v', 'libx264', '-b:v', '4000k', '-preset', 'ultrafast',
            '-c:a', 'copy',
            '-pix_fmt', 'yuv420p',
            '-y', output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, errors='replace', timeout=7200)
        return True, target_w, target_h
    except subprocess.CalledProcessError as e:
        print(f"  ❌ CPU 降级也失败: {e}")
        return False, None, None
    finally:
        if os.path.exists(tmp_list):
            os.remove(tmp_list)


# ======================== macOS 视频封面 ========================

def add_cover_frame(video_path):
    """提取首帧作为视频封面（解决 macOS Finder/QuickLook 预览黑色）"""
    cover_path = video_path + '.cover.jpg'
    tmp_path   = video_path + '.tmp.mp4'
    try:
        subprocess.run([
            'ffmpeg', '-i', video_path,
            '-vframes', '1', '-q:v', '2',
            '-y', cover_path
        ], check=True, capture_output=True, timeout=30)

        subprocess.run([
            'ffmpeg', '-i', video_path,
            '-i', cover_path,
            '-map', '0', '-map', '1',
            '-c', 'copy', '-c:v:1', 'mjpeg',
            '-disposition:v:1', 'attached_pic',
            '-movflags', '+faststart',
            '-y', tmp_path
        ], check=True, capture_output=True, timeout=60)

        os.replace(tmp_path, video_path)
        return True
    except Exception as e:
        print(f"  ⚠️ 封面处理失败: {e}")
        return False
    finally:
        for p in [cover_path, tmp_path]:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except:
                    pass


# ======================== 核心逻辑 ========================

def process_book(book_name, episodes):
    n = len(episodes)
    if n == 0:
        return

    for ep_num, fp in episodes:
        get_video_info(fp)

    max_w = max(get_video_info(fp)['width'] for _, fp in episodes)
    max_h = max(get_video_info(fp)['height'] for _, fp in episodes)
    source_is_landscape = max_w > max_h

    # 确定输出目标列表：(文件夹后缀, 宽, 高, 文件名标签)
    targets = []
    if source_is_landscape:
        targets.append(("横版", 1280, 720, "横"))
        targets.append(("竖版", 720, 1280, "竖"))
        print(f"\n📁 《{book_name}》 共 {n} 集 (横版源 → 输出横版+竖版)")
    else:
        targets.append(("竖版", 720, 1280, "竖"))
        print(f"\n📁 《{book_name}》 共 {n} 集 (竖版源 → 输出竖版)")

    print(f"   水印: 左上「《{book_name}」+ 右侧竖排「无不良引导」")

    # 预生成水印（每本书只用一次），书名宽度按输出最大宽度计算
    max_title_width = min(max_w, 1280) - 40
    title_png, disc_png = build_overlay_filter(book_name, max_title_width)

    date_str = datetime.now().strftime("%m%d")

    for orient_suffix, target_w, target_h, orient_label in targets:
        out_dir = os.path.join(OUTPUT_DIR, f"{book_name}-{orient_suffix}")
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
            out_name = f"{book_name}-ai-{orient_label}-{date_str}-{seq:03d}.mp4"
            out_path = os.path.join(out_dir, out_name)

            if os.path.exists(out_path):
                size = os.path.getsize(out_path) / (1024*1024)
                print(f"  ⏭️  已存在: {out_name} ({size:.0f}MB)")
            else:
                eps_range = f"{episodes[i][0]}-{episodes[j-1][0]}"
                print(f"  🎬 第{eps_range}集 → {out_name} ({total:.0f}s, {target_w}×{target_h})")
                ok, ow, oh = concat_videos(files, out_path, title_png, disc_png, target_w, target_h)
                if ok:
                    sz = os.path.getsize(out_path) / (1024*1024)
                    print(f"     ✅ {sz:.0f}MB {ow}×{oh}")
                    if sys.platform == 'darwin':
                        add_cover_frame(out_path)
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
