# main.py
import os
import sys
import shutil
import subprocess
import json
import re
from pathlib import Path

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
ASPECT_RATIO_TOL = 0.01


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
        ], capture_output=True, check=True)

        # 手动解码，使用utf-8并忽略错误
        stdout_bytes = result.stdout
        stdout_str = stdout_bytes.decode('utf-8', errors='ignore') if stdout_bytes else ''
        
        # 清理和修复JSON字符串
        if not stdout_str:
            print(f"⚠️ ffprobe 未返回数据: {video_path}")
            return None
            
        # 1. 移除可能的BOM（Byte Order Mark）
        json_str = stdout_str.lstrip('\ufeff')
        
        # 2. 移除所有控制字符，只保留制表符、换行符和回车符
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
        
        # 3. 修复JSON解析的核心问题：使用更简单可靠的方法处理ffprobe输出
        # ffprobe输出的JSON格式问题通常出在字符串值中包含特殊字符
        try:
            # 尝试直接解析原始JSON
            probe_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            # 解析失败，尝试更严格的清理
            print(f"⚠️ 原始JSON解析失败，尝试修复: {video_path}")
            
            # 修复1: 移除所有可能导致问题的特殊字符，只保留ASCII可打印字符
            json_str = re.sub(r'[^\x20-\x7e]', '', json_str)
            
            # 修复2: 修复未转义的引号 - 使用更精确的正则表达式
            # 匹配键值对中的字符串值，确保只替换值内的未转义引号
            json_str = re.sub(r'"([^"]*?)(?<!\\)"', lambda m: '"' + m.group(1).replace('"', '\\"') + '"', json_str)
            
            # 修复3: 修复可能的尾随逗号
            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            
            # 修复4: 确保JSON只包含一个顶级对象
            # 有些ffprobe输出可能包含额外内容，只保留第一个完整的JSON对象
            json_match = re.search(r'\{[\s\S]*?\}', json_str)
            if json_match:
                json_str = json_match.group(0)
            
            try:
                # 再次尝试解析修复后的JSON
                probe_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                # 仍然解析失败，打印详细错误信息
                print(f"❌ JSON修复后仍解析失败: {video_path}")
                print(f"   错误位置: 行 {e.lineno}, 列 {e.colno}")
                print(f"   错误信息: {e.msg}")
                # 打印出错位置附近的内容
                lines = json_str.split('\n')
                if e.lineno <= len(lines):
                    start = max(0, e.lineno - 2)
                    end = min(len(lines), e.lineno + 1)
                    print(f"   上下文 ({start+1}-{end}行):")
                    for i in range(start, end):
                        line = lines[i]
                        marker = "--->" if i == e.lineno - 1 else "    "
                        print(f"   {marker} {i+1}: {line}")
                        if i == e.lineno - 1:
                            print(f"   {marker}      {' '*(e.colno-1)}^ 错误位置")
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
            'fps': fps,
            'has_audio': has_audio
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

    # 延迟导入ffmpeg，减少启动时间
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

    # 处理音频：如果原视频有音频，保留音频轨道
    has_audio = info.get('has_audio', False)
    if has_audio:
        # 保留音频轨道，不做转码处理
        audio = input_stream.audio
        output_args = [video, audio, output_path]
    else:
        # 没有音频，只处理视频轨道
        output_args = [video, output_path]

    print(f"🔄 正在处理: {input_path} → {output_path}")
    try:
        (
            ffmpeg_lib
            .output(*output_args, **output_opts)
            .overwrite_output()
            .run(cmd=FFMPEG_PATH, quiet=True)
        )
        print(f"✔️ 完成: {output_path}")
    except Exception as e:
        print(f"❌ 处理失败 {input_path}: {e}")


def process_all_videos(input_dir: Path, output_dir: Path):
    import_tkinter()
    if not input_dir.exists():
        messagebox.showerror("错误", "输入文件夹不存在！")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"}
    videos = [f for f in input_dir.rglob("*") if f.suffix.lower() in video_extensions]

    if not videos:
        messagebox.showinfo("提示", "输入文件夹中没有找到视频文件！")
        return

    for video_file in videos:
        # 先获取视频信息，检查是否有音频
        video_info = get_video_info(str(video_file))
        has_audio = video_info.get('has_audio', True) if video_info else True
        
        # 生成输出文件名
        if has_audio:
            output_file = output_dir / video_file.name
        else:
            # 没有音频，在文件名后添加醒目标识（重复两遍+Windows允许的符号）
            output_filename = f"{video_file.stem}_【无音频】【无音频】{video_file.suffix}"
            output_file = output_dir / output_filename
            print(f"🔇 检测到无音频视频: {video_file.name}")
            print(f"📝 将添加标识并重命名为: {output_filename}")
            
        print(f"\n--- 处理: {video_file.name} ---")
        process_video(str(video_file), str(output_file))

    import_tkinter()
    messagebox.showinfo("完成", f"所有视频处理完毕！\n共处理 {len(videos)} 个文件。")


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
        "│  🚀 千川投流视频格式转换工具                     \n"
        "├────────────────────────────────────────────────┤\n"
        "│    使用说明：                                   \n"
        "│    📍 1. 选择待转换视频所在文件夹                \n"
        "│    📍 2. 指定输出目录                            \n"
        "│    📍 3. 等待处理完成                            \n"
        "├────────────────────────────────────────────────┤\n"
        "│  💡 新增功能：V1.1 新增无音频标识 | 批量处理      \n"
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