# 千川投流视频格式转换

> 一键将竖屏视频批量转换为符合抖音千川/快手等广告平台要求的竖屏格式

当前版本：`v1.5.0`

## 📌 视频规范要求

| 参数 | 要求 |
|------|------|
| 宽高比 | 9:16（竖版） |
| 分辨率 | 720×1280 ~ 1440×2560 |
| 视频码率 | ≥ 516 kbps |
| 文件大小 | ≤ 1000 MB |

## ✨ 功能特点

- 📁 **批量处理** - 支持批量转换多个视频文件
- 🔍 **智能检测** - 自动检测视频是否符合平台规范
- ⚡ **极速处理** - 符合规范的视频直接复制，无需转码
- ✂️ **智能裁剪** - 不符合规范时自动裁剪并转码，保持最佳画质
- 🔇 **无音频识别** - 自动识别无音频视频并添加标识
- 📂 **目录保持** - 支持子文件夹递归处理，保持原目录结构
- 🎁 **开箱即用** - 无需安装 FFmpeg，下载即可使用
- 🧭 **清晰日志** - 转换时输出当前文件、原因和耗时，方便定位异常素材

## 🚀 使用方法

### 第一步：下载程序

前往 [Releases](https://github.com/vivalucas/qianchuan_processor/releases) 下载对应系统的最新版本：

- Windows：`qianchuan_processor_vX.X.X.exe`
- macOS Apple Silicon（M 芯片）：`qianchuan_processor_vX.X.X_macos_arm64.tar.gz`

### 第二步：运行程序

- Windows：双击运行 `qianchuan_processor_vX.X.X.exe`
- macOS：解压 `.tar.gz` 后运行其中的可执行文件

程序启动后会弹出文件夹选择对话框。

### 第三步：选择文件夹

1. **选择输入文件夹** - 选择包含待转换视频的文件夹
2. **选择输出文件夹** - 选择处理后视频的保存位置

### 第四步：等待处理

程序会自动处理所有视频，并在完成后显示处理结果

## 📂 目录结构说明

程序支持处理子文件夹中的视频，会保持原目录结构输出：

```
输入文件夹 (input)
├── 视频1.mp4              → 输出: output/视频1.mp4
├── 子文件夹A/
│   ├── 视频2.mp4          → 输出: output/子文件夹A/视频2.mp4
│   └── 子子文件夹/
│       └── 视频3.mp4      → 输出: output/子文件夹A/子子文件夹/视频3.mp4
└── 空文件夹/               ← 无视频，不创建输出目录
```

## ⚠️ 注意事项

- 无音频的视频会在文件名后添加 `_【无音频】` 标识
- 符合规范的视频会直接复制，处理速度极快
- 不符合规范的视频会自动裁剪为 1080×1920 并转码
- 大于 1000 MB 的视频会进入转码流程，尽量压缩到平台友好的体积
- 输出文件夹不能与输入文件夹相同，避免覆盖原始素材
- 如果视频数量较多，处理时间可能会较长，请耐心等待

## 🛠️ 开发与构建

本项目使用 Python 和 PyInstaller 构建。开发环境建议使用 `uv`：

```bash
uv sync
```

本地 Windows 构建示例：

```bash
uv run pyinstaller --onefile --name qianchuan_processor_v1.5.0 --icon assets/app.ico --add-data "ffmpeg;ffmpeg" --hidden-import=ffmpeg --hidden-import=tkinter --optimize 2 --exclude-module=pip --exclude-module=setuptools --exclude-module=distutils main.py
```

图标源文件在 `assets/app-icon.svg`，平台图标为 `assets/app.ico` 和 `assets/app.icns`。如需重新生成图标：

```bash
uv run python tools/create_icons.py
```

## 📌 版本更新

### v1.5.0 (2026-05-12)
- 🎨 新增应用图标，Windows 和 macOS 构建产物会带有清晰的品牌标识
- 📏 补齐 1000 MB 文件大小检查，README 与实际处理逻辑保持一致
- 🔊 转码时显式复制音频轨道，避免无意重编码
- 🧾 优化命令行启动文案和转换原因提示
- 🧹 优化 `.gitignore` 和项目元数据，减少本地构建产物误提交

### v1.4 (2026-05-12)
- 🛡️ 新增 ffprobe/ffmpeg 超时保护，避免单个异常视频卡住整批处理
- ⏳ 转码中每 30 秒输出处理状态，方便定位当前卡在哪个文件
- 📂 子文件夹处理改为完整递归，保持原目录结构
- 🍎 GitHub Actions 新增 macOS Apple Silicon（M 芯片）构建产物
- 🐛 修复 Windows 控制台编码导致的崩溃问题
- 🐛 修复无音频文件名标识重复问题

### v1.3 (2026-02-28)
- ✨ 新增支持两层子文件夹递归处理
- 📂 保持原目录结构输出
- 🚫 空文件夹不创建

### v1.2 (2026-01-20)
- 🐛 修复视频信息解析失败问题，提高JSON解析健壮性
- ✨ 新增无音频视频自动识别功能
- 🔍 无音频视频自动添加标识

## 📧 问题反馈

如遇到问题，请发送邮件至：lucas6.zju@vip.163.com
