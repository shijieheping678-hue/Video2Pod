# AI Video Podcast Generator

将短视频一键转化为高质量双人对话播客，支持语音克隆、AI 文案改写和动画视频渲染。

## 功能概览

- **视频输入** — 上传本地文件或从 B站/YouTube 下载视频
- **语音识别 (ASR)** — 支持阿里 DashScope (Qwen3-ASR) 和火山引擎双引擎
- **AI 文案改写** — 使用 DeepSeek 大模型将原始转写重写为自然的双人播客对话
- **双人配音 (TTS)** — 支持 Edge TTS (免费) 和火山引擎 (含声音克隆)
- **视频合成** — FFmpeg 快速合成或 Remotion 动画渲染，自动生成字幕
- **任务管理** — 多任务持久化存储，随时恢复中断的工作流

## 技术架构

```
视频/音频输入 → 语音识别 (ASR) → AI 文案改写 → 双人 TTS 合成 → 视频渲染
```

### 技术栈

| 层级 | 技术 |
|------|------|
| Web UI | Streamlit |
| 视频下载 | yt-dlp |
| 语音识别 | DashScope (阿里) / Volcengine (火山引擎) |
| AI 改写 | DeepSeek (OpenAI-compatible API) |
| 语音合成 | Edge TTS (免费) / Volcengine TTS + 声音克隆 |
| 视频处理 | FFmpeg / Remotion (React) |
| 语言 | Python 3.10+ / TypeScript (Remotion) |

## 项目结构

```
video-creater/
├── app.py                  # Streamlit 主应用入口
├── run.py                  # 生产环境启动脚本
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量模板
│
├── src/                    # 核心模块
│   ├── utils.py            # 日志与工具函数
│   ├── downloader.py       # 视频下载 (yt-dlp)
│   ├── transcriber.py      # 语音识别 (多引擎)
│   ├── rewriter.py         # AI 文案改写 (DeepSeek)
│   ├── tts.py              # 语音合成与对话拼接
│   ├── voice_cloner.py     # 火山引擎声音克隆
│   ├── video_maker.py      # 视频渲染 (FFmpeg/Remotion)
│   ├── task_manager.py     # 任务持久化管理
│   ├── volc_service.py     # 火山引擎统一服务 (TOS/ASR/TTS)
│   ├── edge_voices.py      # Edge TTS 音色配置
│   └── volc_voices.py      # 火山引擎音色配置
│
├── remotion-video/         # Remotion 视频渲染项目
│   ├── package.json
│   └── src/
│       ├── index.tsx        # Remotion 入口
│       ├── Root.tsx         # 根组件
│       ├── MyComposition.tsx # 视频动画组件
│       └── style.css
│
├── tasks/                  # 任务数据存储 (运行时生成)
```

## 快速开始

### 前置要求

- **Python** 3.10+
- **FFmpeg** — 需加入系统 PATH ([下载地址](https://ffmpeg.org/download.html))
- **Node.js** 18+ — 仅 Remotion 渲染需要 (可选)

### 1. 克隆项目

```bash
git clone https://github.com/your-username/video-creater.git
cd video-creater
```

### 2. 安装 Python 依赖

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 配置环境变量

复制模板并填入你的 API 密钥：

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少配置以下一组：

```ini
# DeepSeek (文案改写 - 必需)
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 以下二选一 (语音识别)

# 方案 A: 阿里 DashScope
DASHSCOPE_API_KEY=your_key_here

# 方案 B: 火山引擎
VOLC_ACCESS_KEY=your_key_here
VOLC_SECRET_KEY=your_key_here
VOLC_APPID=your_appid
VOLC_ACCESS_TOKEN=your_token
```

完整的环境变量说明见 [环境变量参考](#环境变量参考)。

### 4. 安装 Remotion 依赖 (可选)

如果需要使用 Remotion 动画渲染引擎：

```bash
cd remotion-video
npm install
cd ..
```

### 5. 启动应用

```bash
# 开发模式
streamlit run app.py

# 或使用启动脚本 (headless 模式)
python run.py
```

浏览器访问 `http://localhost:8501` 即可使用。

## 使用流程

### 步骤 1: 视频源

1. 选择 ASR 引擎 (DashScope 或 Volcengine)
2. 上传本地视频/音频文件，或粘贴 B站/YouTube 链接
3. 点击「开始处理」，系统自动提取音频并转写为文字

### 步骤 2: 文案处理

1. 查看原始转写文本
2. 点击「AI 生成播客文案」，DeepSeek 将自动改写为双人对话
3. 可在编辑框中手动修改文案

### 步骤 3: 合成预览

1. 在侧边栏配置主持人/嘉宾音色和语速
2. 点击「生成双人对话语音」
3. 上传背景封面图片 (16:9 最佳)
4. 选择渲染引擎 (FFmpeg 快速版 / Remotion 动画版)
5. 点击「合成最终视频」，完成后可在线预览和下载

## 环境变量参考

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 (文案改写) |
| `DEEPSEEK_BASE_URL` | 否 | API 地址，默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 否 | 模型名称，默认 `deepseek-chat` |
| `DASHSCOPE_API_KEY` | 二选一 | 阿里 DashScope API 密钥 (ASR) |
| `VOLC_ACCESS_KEY` | 二选一 | 火山引擎 IAM Access Key |
| `VOLC_SECRET_KEY` | 二选一 | 火山引擎 IAM Secret Key |
| `VOLC_APPID` | 火山引擎需要 | 火山引擎应用 ID |
| `VOLC_ACCESS_TOKEN` | 火山引擎需要 | 火山引擎 Access Token |
| `VOLC_APPKEY` | V2/V3 需要 | 火山引擎 App Key (BigModel) |
| `VOLC_ASR_VERSION` | 否 | ASR 版本: `v1` 或 `v2`，默认 `v1` |
| `VOLC_ASR_CLUSTER` | 否 | ASR 集群，默认 `volc_auc_common` |
| `VOLC_REGION` | 否 | 地域，默认 `cn-beijing` |
| `VOLC_TOS_ENDPOINT` | 火山引擎需要 | TOS 存储端点 |
| `VOLC_TOS_BUCKET` | 火山引擎需要 | TOS 存储桶名称 |
| `VOLC_TOS_FOLDER` | 否 | TOS 文件夹前缀，默认 `podcast-inputs/` |

## 音色配置

### Edge TTS (免费)

| 音色 ID | 描述 |
|---------|------|
| `zh-CN-YunyangNeural` | 云扬 — 男声，专业稳重 |
| `zh-CN-YunxiNeural` | 云希 — 男声，阳光活泼 |
| `zh-CN-XiaoxiaoNeural` | 晓晓 — 女声，温暖亲切 |

### 火山引擎

| 音色 ID | 描述 |
|---------|------|
| `BV001_streaming` | 通用女声 (免费) |
| `BV002_streaming` | 通用男声 (免费) |
| `zh_male_dayi_saturn_bigtts` | 大壹 — 大模型男声 |
| `S_xxxxxxx` | 自定义克隆音色 |

## 声音克隆

项目支持通过火山引擎 Mega TTS 进行声音克隆：

```python
from src.voice_cloner import VoiceCloner

cloner = VoiceCloner()

# 1. 上传训练音频
cloner.upload_audio("sample.m4a", "my_voice_id", model_type=4)

# 2. 等待训练完成
cloner.wait_for_training("my_voice_id", timeout=120)

# 3. 在 TTS 中使用克隆 ID
# 将 "my_voice_id" 填入侧边栏的嘉宾音色 ID 即可
```

## License

MIT
