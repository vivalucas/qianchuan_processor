# main.py
import os
import sys
import shutil
import subprocess
import json
import re
import time
from fractions import Fraction
from pathlib import Path


def configure_console_output():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


configure_console_output()

# 延迟导入tkinter，减少启动时间
def import_tkinter():
    global tk, filedialog, messagebox
    import tkinter as tk
    from tkinter import filedialog, messagebox


# 注意：不再直接依赖 ffmpeg.probe，改用 subprocess 调用 ffprobe（更可靠）
# 但仍保留 ffmpeg-python 用于视频处理（编码部分没问题）

def get_ffmpeg_paths():
    """返回 ffmpeg 和 ffprobe 的路径（支持打包后和开发环境）"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    if sys.platform == "win32":
        ffmpeg_path = os.path.join(base_path, "ffmpeg", "ffmpeg.exe")
        ffprobe_path = os.path.join(base_path, "ffmpeg", "ffprobe.exe")
    else:
        ffmpeg_path = os.path.join(base_path, "ffmpeg", "ffmpeg")
        ffprobe_path = os.path.join(base_path, "ffmpeg", "ffprobe")
    return ffmpeg_path, ffprobe_path


FFMPEG_PATH, FFPROBE_PATH = get_ffmpeg_paths()

# =============== 视频信息获取（使用 subprocess，避免 probe 模块问题） ===============
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30
TARGET_BITRATE_K = 1000
MIN_BITRATE_K = 516
MAX_FILE_SIZE_MB = 1000
NO_AUDIO_SUFFIX = "_【无音频】"
APP_VERSION = "1.5.0"
ASPECT_RATIO_TOL = 0.01
FFPROBE_TIMEOUT_SECONDS = 60
TRANSCODE_MIN_TIMEOUT_SECONDS = 10 * 60
TRANSCODE_MAX_TIMEOUT_SECONDS = 2 * 60 * 60
PROGRESS_LOG_INTERVAL_SECONDS = 30


def parse_frame_rate(frame_rate):
    """Safely parse ffprobe frame-rate strings such as 30000/1001."""
    try:
        fps = float(Fraction(str(frame_rate)))
        return fps if fps > 0 else float(TARGET_FPS)
    except (ValueError, ZeroDivisionError):
        return float(TARGET_FPS)


def parse_ffprobe_json(stdout_bytes):
    """Parse ffprobe JSON while tolerating BOMs and stray control characters."""
    stdout_str = stdout_bytes.decode('utf-8', errors='ignore') if stdout_bytes else ''
    if not stdout_str:
        return None

    json_str = stdout_str.lstrip('\ufeff')
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        start = json_str.find('{')
        if start == -1:
            raise
        decoder = json.JSONDecoder()
        probe_data, _ = decoder.raw_decode(json_str[start:])
        return probe_data


def format_elapsed(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分{seconds}秒"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def get_transcode_timeout_seconds(info):
    duration = info.get('duration_seconds') or 0
    if duration <= 0:
        return TRANSCODE_MAX_TIMEOUT_SECONDS
    return min(
        TRANSCODE_MAX_TIMEOUT_SECONDS,
        max(TRANSCODE_MIN_TIMEOUT_SECONDS, int(duration * 20 + 300))
    )


def get_no_audio_output_name(video_file: Path):
    if video_file.stem.endswith(NO_AUDIO_SUFFIX):
        return video_file.name
    return f"{video_file.stem}{NO_AUDIO_SUFFIX}{video_file.suffix}"


def run_ffmpeg_with_progress(command, input_path, timeout_seconds):
    start_time = time.monotonic()
    next_progress_time = start_time + PROGRESS_LOG_INTERVAL_SECONDS
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    while True:
        return_code = process.poll()
        if return_code is not None:
            if return_code == 0:
                return True
            print(f"❌ ffmpeg 退出码 {return_code}: {input_path}")
            return False

        now = time.monotonic()
        elapsed = now - start_time
        if elapsed >= timeout_seconds:
            process.kill()
            process.wait()
            print(f"⏱️ 处理超时，已跳过: {input_path}（耗时 {format_elapsed(elapsed)}）")
            return False

        if now >= next_progress_time:
            print(f"⏳ 仍在处理: {input_path}（已耗时 {format_elapsed(elapsed)}）")
            next_progress_time = now + PROGRESS_LOG_INTERVAL_SECONDS

        time.sleep(1)


def get_video_info(video_path):
    """使用 ffprobe 获取视频信息（JSON 格式），不依赖 ffmpeg-python 的 probe"""
    try:
        if not os.path.exists(FFPROBE_PATH):
            print(f"❌ ffprobe 不存在: {FFPROBE_PATH}")
            return None

        # 不使用text=True，手动处理编码，避免gbk解码错误
        result = subprocess.run([
            FFPROBE_PATH,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            video_path
        ], capture_output=True, check=True, timeout=FFPROBE_TIMEOUT_SECONDS)

        probe_data = parse_ffprobe_json(result.stdout)
        if not probe_data:
            print(f"⚠️ ffprobe 未返回数据: {video_path}")
            return None

        video_stream = None
        has_audio = False
        for stream in probe_data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
            elif stream.get('codec_type') == 'audio':
                has_audio = True

        if not video_stream:
            return None

        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        r_frame_rate = video_stream.get('r_frame_rate', '30/1')
        fps = parse_frame_rate(r_frame_rate)

        bitrate_str = video_stream.get('bit_rate') or probe_data.get('format', {}).get('bit_rate')
        bitrate_kbps = int(bitrate_str) // 1000 if bitrate_str and bitrate_str.isdigit() else 0
        duration_str = probe_data.get('format', {}).get('duration')
        try:
            duration_seconds = float(duration_str) if duration_str else 0
        except ValueError:
            duration_seconds = 0
        try:
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        except OSError:
            file_size_mb = 0

        return {
            'width': width,
            'height': height,
            'bitrate_kbps': bitrate_kbps,
            'fps': fps,
            'has_audio': has_audio,
            'duration_seconds': duration_seconds,
            'file_size_mb': file_size_mb
        }
    except subprocess.CalledProcessError as e:
        print(f"⚠️ ffprobe 执行失败 {video_path}: {e}")
        return None
    except subprocess.TimeoutExpired:
        print(f"⏱️ ffprobe 超时，跳过视频: {video_path}")
        return None
    except Exception as e:
        print(f"⚠️ 无法解析视频信息 {video_path}: {e}")
        return None


# =============== 其余逻辑保持不变 ===============
def is_valid_resolution(w, h):
    return (720 <= w <= 1440) and (1280 <= h <= 2560)


def is_valid_aspect_ratio(w, h):
    ratio = w / h
    target_ratio = 9 / 16
    return abs(ratio - target_ratio) <= ASPECT_RATIO_TOL


def process_video(input_path, output_path, info=None):
    output_file = Path(output_path)
    input_file = Path(input_path)
    if input_file.resolve() == output_file.resolve():
        print(f"❌ 输出文件与输入文件相同，跳过以避免覆盖原视频: {input_path}")
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    info = info or get_video_info(input_path)
    if not info:
        print(f"❌ 跳过无效视频: {input_path}")
        return False

    w, h = info['width'], info['height']
    bitrate = info['bitrate_kbps']
    if w <= 0 or h <= 0:
        print(f"❌ 视频尺寸无效，跳过: {input_path}")
        return False

    aspect_ok = is_valid_aspect_ratio(w, h)
    res_ok = is_valid_resolution(w, h)
    bitrate_ok = bitrate >= MIN_BITRATE_K
    size_ok = info.get('file_size_mb', 0) <= MAX_FILE_SIZE_MB

    if aspect_ok and res_ok and bitrate_ok and size_ok:
        print(f"✅ 已符合平台要求，直接复制: {input_path}")
        try:
            shutil.copy2(input_path, output_path)
        except Exception as e:
            print(f"❌ 复制失败: {e}")
            return False
        return True

    reasons = []
    if not aspect_ok:
        reasons.append("比例不是 9:16")
    if not res_ok:
        reasons.append("分辨率不在 720×1280 ~ 1440×2560")
    if not bitrate_ok:
        reasons.append(f"码率低于 {MIN_BITRATE_K} kbps")
    if not size_ok:
        reasons.append(f"文件大于 {MAX_FILE_SIZE_MB} MB")
    print(f"🛠️ 需要转换: {'；'.join(reasons)}")

    # 延迟导入ffmpeg，减少启动时间
    try:
        import ffmpeg as ffmpeg_lib
    except ImportError:
        print("❌ 未安装 ffmpeg-python，无法处理视频")
        return False

    src_w, src_h = w, h
    target_w, target_h = TARGET_WIDTH, TARGET_HEIGHT

    scale_w = target_w
    scale_h = int(src_h * (target_w / src_w))
    if scale_h < target_h:
        scale_h = target_h
        scale_w = int(src_w * (target_h / src_h))

    x = max(0, (scale_w - target_w) // 2)
    y = max(0, (scale_h - target_h) // 2)

    input_stream = ffmpeg_lib.input(input_path)
    video = (
        input_stream
        .filter('scale', scale_w, scale_h)
        .filter('crop', target_w, target_h, x, y)
    )

    if not bitrate_ok or not aspect_ok or not res_ok or not size_ok:
        video = video.filter('fps', fps=TARGET_FPS)
        output_opts = {
            'vcodec': 'libx264',
            'video_bitrate': f'{TARGET_BITRATE_K}k',
            'preset': 'fast',
            'pix_fmt': 'yuv420p'
        }
    else:
        output_opts = {}

    # 处理音频：如果原视频有音频，保留音频轨道
    has_audio = info.get('has_audio', False)
    if has_audio:
        # 保留音频轨道，不做转码处理
        audio = input_stream.audio
        output_args = [video, audio, output_path]
        output_opts['acodec'] = 'copy'
    else:
        # 没有音频，只处理视频轨道
        output_args = [video, output_path]

    print(f"🔄 正在处理: {input_path} → {output_path}")
    try:
        output_stream = (
            ffmpeg_lib
            .output(*output_args, **output_opts)
            .overwrite_output()
        )
        command = output_stream.compile(cmd=FFMPEG_PATH)
        timeout_seconds = get_transcode_timeout_seconds(info)
        if not run_ffmpeg_with_progress(command, input_path, timeout_seconds):
            return False
        print(f"✔️ 完成: {output_path}")
        return True
    except Exception as e:
        print(f"❌ 处理失败 {input_path}: {e}")
        return False


def process_all_videos(input_dir: Path, output_dir: Path):
    import_tkinter()
    if not input_dir.exists():
        messagebox.showerror("错误", "输入文件夹不存在！")
        return

    resolved_input_dir = input_dir.resolve()
    resolved_output_dir = output_dir.resolve()
    if resolved_input_dir == resolved_output_dir:
        messagebox.showerror("错误", "输出文件夹不能与输入文件夹相同！")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"}

    video_list = []

    for video_file in input_dir.rglob("*"):
        if not video_file.is_file() or video_file.suffix.lower() not in video_extensions:
            continue

        resolved_video = video_file.resolve()
        try:
            resolved_video.relative_to(resolved_output_dir)
            continue
        except ValueError:
            pass

        rel_path = video_file.parent.resolve().relative_to(resolved_input_dir)
        video_list.append((video_file, rel_path))

    if not video_list:
        messagebox.showinfo("提示", "输入文件夹中没有找到视频文件！")
        return

    processed_count = 0
    failed_count = 0

    total_count = len(video_list)
    for index, (video_file, rel_path) in enumerate(video_list, start=1):
        try:
            print(f"\n--- 处理({index}/{total_count}): {video_file.name} ---")
            if rel_path != Path("."):
                print(f"📂 路径: {rel_path}")

            video_info = get_video_info(str(video_file))
            if not video_info:
                failed_count += 1
                print(f"❌ 无法读取视频信息，已跳过: {video_file}")
                continue

            has_audio = video_info.get('has_audio', True)

            if has_audio:
                output_file = output_dir / rel_path / video_file.name
            else:
                output_filename = get_no_audio_output_name(video_file)
                output_file = output_dir / rel_path / output_filename
                print(f"🔇 检测到无音频视频: {video_file.name}")
                print(f"📝 将添加标识并重命名为: {output_filename}")

            if process_video(str(video_file), str(output_file), video_info):
                processed_count += 1
            else:
                failed_count += 1
        except Exception as e:
            failed_count += 1
            print(f"❌ 处理异常，已跳过 {video_file}: {e}")

    messagebox.showinfo("完成", f"视频处理完毕！\n成功: {processed_count} 个\n失败/跳过: {failed_count} 个。")


# =============== GUI ===============
def select_folder(title):
    import_tkinter()
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title=title)
    root.destroy()
    return folder


def main_gui():
    print(
        "┌────────────────────────────────────────────────┐\n"
        f"│  🚀 千川投流视频格式转换工具 v{APP_VERSION:<18}\n"
        "├────────────────────────────────────────────────┤\n"
        "│    使用说明：                                   \n"
        "│    📍 1. 选择待转换视频所在文件夹                \n"
        "│    📍 2. 指定输出目录                            \n"
        "│    📍 3. 等待处理完成                            \n"
        "├────────────────────────────────────────────────┤\n"
        "│  💡 支持递归处理、无音频标识、超时保护和文件大小检查       \n"
        "│  📧 问题反馈：lucas6.zju@vip.163.com            \n"
        "├────────────────────────────────────────────────┤\n"
        "│  ⏳ 正在启动工具...                              \n"
        "└────────────────────────────────────────────────┘"
    )
    input_folder = select_folder("请选择输入视频文件夹")
    if not input_folder:
        print("未选择输入文件夹，退出。")
        return

    output_folder = select_folder("请选择输出视频文件夹")
    if not output_folder:
        print("未选择输出文件夹，退出。")
        return

    print(f"输入: {input_folder}")
    print(f"输出: {output_folder}")

    process_all_videos(Path(input_folder), Path(output_folder))


if __name__ == "__main__":
    main_gui()
