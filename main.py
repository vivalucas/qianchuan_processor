# main.py
import os
import sys
import shutil
import subprocess
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path


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
ASPECT_RATIO_TOL = 0.01


def get_video_info(video_path):
    """使用 ffprobe 获取视频信息（JSON 格式），不依赖 ffmpeg-python 的 probe"""
    try:
        if not os.path.exists(FFPROBE_PATH):
            print(f"❌ ffprobe 不存在: {FFPROBE_PATH}")
            return None

        result = subprocess.run([
            FFPROBE_PATH,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            video_path
        ], capture_output=True, text=True, check=True)

        probe_data = json.loads(result.stdout)
        video_stream = None
        for stream in probe_data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break

        if not video_stream:
            return None

        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        r_frame_rate = video_stream.get('r_frame_rate', '30/1')
        try:
            fps = eval(r_frame_rate) if '/' in r_frame_rate else float(r_frame_rate)
        except:
            fps = 30.0

        bitrate_str = video_stream.get('bit_rate') or probe_data.get('format', {}).get('bit_rate')
        bitrate_kbps = int(bitrate_str) // 1000 if bitrate_str and bitrate_str.isdigit() else 0

        return {
            'width': width,
            'height': height,
            'bitrate_kbps': bitrate_kbps,
            'fps': fps
        }
    except subprocess.CalledProcessError as e:
        print(f"⚠️ ffprobe 执行失败 {video_path}: {e}")
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


def process_video(input_path, output_path):
    info = get_video_info(input_path)
    if not info:
        print(f"❌ 跳过无效视频: {input_path}")
        return

    w, h = info['width'], info['height']
    bitrate = info['bitrate_kbps']

    aspect_ok = is_valid_aspect_ratio(w, h)
    res_ok = is_valid_resolution(w, h)
    bitrate_ok = bitrate >= MIN_BITRATE_K

    if aspect_ok and res_ok and bitrate_ok:
        print(f"✅ 符合要求，直接复制: {input_path}")
        try:
            shutil.copy2(input_path, output_path)
        except Exception as e:
            print(f"❌ 复制失败: {e}")
        return

    # 使用 ffmpeg-python 进行处理（这部分在打包后通常没问题）
    try:
        import ffmpeg as ffmpeg_lib
    except ImportError:
        print("❌ 未安装 ffmpeg-python，无法处理视频")
        return

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

    if not bitrate_ok or not aspect_ok or not res_ok:
        video = video.filter('fps', fps=TARGET_FPS)
        output_opts = {
            'vcodec': 'libx264',
            'video_bitrate': f'{TARGET_BITRATE_K}k',
            'preset': 'fast',
            'pix_fmt': 'yuv420p'
        }
    else:
        output_opts = {}

    print(f"🔄 正在处理: {input_path} → {output_path}")
    try:
        (
            ffmpeg_lib
            .output(video, output_path, **output_opts)
            .overwrite_output()
            .run(cmd=FFMPEG_PATH, quiet=True)
        )
        print(f"✔️ 完成: {output_path}")
    except Exception as e:
        print(f"❌ 处理失败 {input_path}: {e}")


def process_all_videos(input_dir: Path, output_dir: Path):
    if not input_dir.exists():
        messagebox.showerror("错误", "输入文件夹不存在！")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv'}
    videos = [f for f in input_dir.rglob("*") if f.suffix.lower() in video_extensions]

    if not videos:
        messagebox.showinfo("提示", "输入文件夹中没有找到视频文件！")
        return

    for video_file in videos:
        output_file = output_dir / video_file.name
        print(f"\n--- 处理: {video_file.name} ---")
        process_video(str(video_file), str(output_file))

    messagebox.showinfo("完成", f"所有视频处理完毕！\n共处理 {len(videos)} 个文件。")


# =============== GUI ===============
def select_folder(title):
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title=title)
    root.destroy()
    return folder


def main_gui():
    print(
        "┌───────────────────────────────────────┐\n"
        "│  🚀 千川投流视频格式转换工具                \n"
        "├───────────────────────────────────────┤\n"
        "│  💬 问题反馈：lucas6.zju@vip.163.com     \n"
        "│                                       │\n"
        "│  🔹 请先选择待转换视频所在的文件夹           \n"
        "│  🔹 再指定输出目录                        \n"
        "│                                       │\n"
        "│  ⏳ 正在启动工具...                      \n"
        "└───────────────────────────────────────┘"
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