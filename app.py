"""AI Video Podcast Generator — Main Streamlit Application.

A web-based tool that transforms short-form videos into professional
podcast-style content with AI-generated dialogue. The application
provides a three-step workflow:

1. **Video Source**: Upload local files or download from Bilibili/YouTube,
   then extract audio and transcribe speech to text.
2. **Script Processing**: Use DeepSeek AI to rewrite transcripts into
   engaging two-person podcast dialogue scripts.
3. **Synthesis**: Generate dual-voice TTS audio and render the final
   podcast video with subtitles.

Usage:
    Run via ``streamlit run app.py`` or use ``run.py`` for headless mode.
"""

import streamlit as st
import os
import time
from pathlib import Path
from dotenv import load_dotenv

from src.downloader import download_video
from src.transcriber import Transcriber
from src.rewriter import Rewriter
from src.tts import generate_audio_sync, generate_dialogue_audio
from src.video_maker import extract_audio, create_podcast_video, render_remotion_video, start_static_server
from src.utils import logger, ensure_dir, get_filename_from_path
from src.task_manager import TaskManager
from src.edge_voices import EDGE_TTS_VOICES
from src.volc_voices import VOLC_TTS_VOICES

# Load environment variables
load_dotenv()

# Initialize Task Manager
task_manager = TaskManager()

# Page configuration
st.set_page_config(
    page_title="Podcast Generator",
    page_icon="🎙️",
    layout="wide"
)

# Initialize session state
if 'current_task_id' not in st.session_state:
    st.session_state.current_task_id = None

# Helper to load task state into session
def load_task_into_session(task_id):
    """Load a saved task's state into Streamlit session state.

    Reads the task's ``state.json`` and populates ``st.session_state.processing_state``
    with the task's file paths and text data, allowing the UI to resume
    from where the task was last saved.

    Args:
        task_id (str): The task identifier to load.

    Returns:
        bool: True if the task was loaded successfully, False if the task
            state file could not be found.
    """
    task_state = task_manager.load_task(task_id)
    if task_state:
        task_dir = task_manager.get_task_dir(task_id)
        st.session_state.processing_state = {
            'video_path': os.path.join(task_dir, task_state['files']['original_video']) if task_state['files']['original_video'] else None,
            'audio_path': os.path.join(task_dir, task_state['files']['audio']) if task_state['files']['audio'] else None,
            'transcript': task_state['data']['transcript_text'],
            'podcast_script': task_state['data']['script_content'],
            'podcast_audio': os.path.join(task_dir, task_state['files']['podcast_audio']) if task_state['files']['podcast_audio'] else None,
            'final_video': os.path.join(task_dir, task_state['files']['final_video']) if task_state['files']['final_video'] else None
        }
        st.session_state.current_task_id = task_id
        return True
    return False

# Attempt to load if state is empty but ID exists
if st.session_state.current_task_id and 'processing_state' not in st.session_state:
    if not load_task_into_session(st.session_state.current_task_id):
        st.session_state.current_task_id = None # Reset if invalid

if 'processing_state' not in st.session_state:
    st.session_state.processing_state = {
        'video_path': None, 'audio_path': None, 'transcript': None,
        'podcast_script': None, 'podcast_audio': None, 'final_video': None
    }

def main():
    """Render the main Streamlit UI for the Podcast Generator.

    Builds the complete application interface including:
    - Sidebar: Task management (create/load/delete), voice settings,
      speech rate configuration, and background image upload.
    - Tab 1 (Video Source): File upload or URL download with ASR provider selection.
    - Tab 2 (Script Processing): AI-powered script rewriting and manual editing.
    - Tab 3 (Synthesis): TTS generation, video rendering, and download.
    """
    st.title("🎙️ AI 视频播客生成器")
    st.markdown("将短视频一键转化为高质量播客")

    # Sidebar configuration
    with st.sidebar:
        st.header("🗂️ 任务管理")

        # --- New Task Creation Area ---
        with st.expander("➕ 新建任务", expanded=True):
            new_task_name = st.text_input("任务名称", value="我的播客")
            if st.button("确认创建", use_container_width=True):
                task_id = task_manager.create_task(name=new_task_name)
                # Load empty state
                load_task_into_session(task_id)
                st.rerun()

        st.divider()

        # --- Task List with Delete ---
        st.markdown("**历史任务列表**")
        tasks = task_manager.list_tasks()

        for t in tasks:
            col1, col2 = st.columns([4, 1])
            with col1:
                label = f"📂 {t.get('name')} \n_({t.get('created_at')})_"
                if st.session_state.current_task_id == t['id']:
                    st.info(f"当前: {t.get('name')}")
                else:
                    if st.button(label, key=f"load_{t['id']}", use_container_width=True):
                        load_task_into_session(t['id'])
                        st.rerun()
            with col2:
                if st.button("🗑️", key=f"del_{t['id']}", help="删除任务"):
                    task_manager.delete_task(t['id'])
                    if st.session_state.current_task_id == t['id']:
                        st.session_state.current_task_id = None
                        st.session_state.processing_state = {k: None for k in st.session_state.processing_state}
                    st.rerun()


        st.divider()
        st.header("⚙️ 设置")

        # openai_key = st.text_input("OpenAI API Key", value=os.getenv("OPENAI_API_KEY", ""), type="password")
        # dashscope_key = st.text_input("DashScope API Key (阿里百炼)", value=os.getenv("DASHSCOPE_API_KEY", ""), type="password")
        # deepseek_key = st.text_input("DeepSeek API Key", value=os.getenv("DEEPSEEK_API_KEY", ""), type="password")
        # deepseek_base_url = st.text_input("DeepSeek Base URL", value=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))

        st.info("API Key 已通过 .env 配置")

        st.divider()

        st.subheader("角色配音设置")

        # Global Speed Setting
        speech_rate = st.slider("语速调整 (倍速)", 0.8, 2.0, 1.2, 0.1, help="1.0为原速，1.2为推荐播客语速")
        st.divider()

        # Host Config
        st.markdown("**主持人 (Host)**")
        host_provider = st.radio("主持人引擎", ["Edge-TTS (免费)", "Volcengine (火山引擎)"], horizontal=True, key="host_prov")

        host_voice = None
        if host_provider == "Edge-TTS (免费)":
            voice_option = st.selectbox(
                "主持人音色",
                options=EDGE_TTS_VOICES,
                format_func=lambda x: x[1],
                key="host_voice_sel"
            )
            host_voice = voice_option[0]
        else:
            # Volcengine: Select or Input
            volc_mode = st.radio("音色选择方式", ["预置音色", "手动输入ID"], horizontal=True, label_visibility="collapsed")
            if volc_mode == "预置音色":
                voice_option_v = st.selectbox(
                    "火山引擎预置音色",
                    options=VOLC_TTS_VOICES,
                    format_func=lambda x: x[1],
                    key="host_volc_sel"
                )
                host_voice = voice_option_v[0]
            else:
                host_voice = st.text_input("主持人音色 ID (火山)", value="BV001_streaming", key="host_volc_id")

        st.divider()

        # Guest Config
        st.markdown("**嘉宾 (Guest)**")
        guest_provider = st.radio("嘉宾引擎", ["Volcengine (火山引擎 - 克隆音色)", "Edge-TTS (免费)"], horizontal=True, key="guest_prov")

        guest_voice = None
        if guest_provider == "Volcengine (火山引擎 - 克隆音色)":
            guest_voice = st.text_input("嘉宾音色 ID (填入你的克隆 ID)", value="S_0VWdKj6T1", help="在此填入你在火山引擎训练的声音复刻 ID", key="guest_volc_id")
        else:
             voice_option_g = st.selectbox(
                "嘉宾音色",
                options=EDGE_TTS_VOICES,
                format_func=lambda x: x[1],
                key="guest_voice_sel"
            )
             guest_voice = voice_option_g[0]

        st.divider()

        bg_image = st.file_uploader("上传背景封面 (16:9 最佳)", type=["jpg", "png", "jpeg"])

        # Save API keys to environment for this session if provided
        # if dashscope_key:
        #     os.environ["DASHSCOPE_API_KEY"] = dashscope_key
        # if deepseek_key:
        #     os.environ["DEEPSEEK_API_KEY"] = deepseek_key

    # Main content
    tab1, tab2, tab3 = st.tabs(["1️⃣ 视频源", "2️⃣ 文案处理", "3️⃣ 合成预览"])

    # --- TAB 1: Video Source ---
    with tab1:
        st.header("上传或下载视频")

        # ASR Settings
        asr_provider = st.radio("语音识别引擎 (ASR)", ["DashScope (阿里百炼)", "Volcengine (火山引擎)"], horizontal=True)
        st.session_state['asr_provider'] = "volc" if "Volcengine" in asr_provider else "dashscope"

        source_type = st.radio("选择来源", ["上传本地文件", "粘贴视频链接 (B站/YouTube)"])

        if source_type == "上传本地文件":
            uploaded_file = st.file_uploader("拖拽文件到这里 (视频/音频)", type=["mp4", "mov", "mkv", "mp3", "wav", "m4a"])
            if uploaded_file:
                # Preview logic needs to be careful not to lock file
                # Strategy: Create task immediately if not exists, save directly to task dir

                # Check if we have an active task, if not, wait for user action OR create temp preview?
                # To avoid lock, we can display from memory buffer if small, but st.video needs file.

                # Let's save to temp just for PREVIEW (if no task started)
                # But when "Start Processing" is clicked, we save DIRECTLY from uploaded_file buffer to Task Dir.
                # We don't touch the temp file for processing.

                ensure_dir("temp")
                temp_preview_path = os.path.join("temp", f"preview_{uploaded_file.name}")
                if not os.path.exists(temp_preview_path):
                    with open(temp_preview_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                # Show preview
                if uploaded_file.name.lower().endswith(('.mp4', '.mov', '.mkv')):
                    st.video(temp_preview_path)
                else:
                    st.audio(temp_preview_path)

                if st.button("开始处理此文件", key="process_upload"):
                    # 1. Create Task if not exists
                    if not st.session_state.current_task_id:
                        task_name = os.path.splitext(uploaded_file.name)[0]
                        task_id = task_manager.create_task(name=task_name)
                        st.session_state.current_task_id = task_id
                        load_task_into_session(task_id)

                    task_id = st.session_state.current_task_id
                    task_dir = task_manager.get_task_dir(task_id)

                    # 2. Save Original File DIRECTLY to Task Dir (Avoid Copy/Move)
                    original_filename = uploaded_file.name
                    final_path = os.path.join(task_dir, original_filename)

                    with open(final_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    # Update State manually since we bypassed update_task_file
                    task_state = task_manager.load_task(task_id)
                    task_state['files']['original_video'] = original_filename
                    task_manager.save_task_state(task_id, task_state)

                    st.session_state.processing_state['video_path'] = final_path

                    # 3. Process
                    process_video_step(final_path, task_id)
                    st.rerun()

        else:
            video_url = st.text_input("请输入视频链接")
            if st.button("下载并处理", key="process_url"):
                if not video_url:
                    st.error("请输入链接")
                else:
                    try:
                        with st.status("正在下载视频...", expanded=True) as status:
                            # 1. Create Task
                            task_id = task_manager.create_task(name="Online Video")
                            st.session_state.current_task_id = task_id
                            task_dir = task_manager.get_task_dir(task_id)

                            # 2. Download DIRECTLY to Task Dir
                            # download_video defaults to current dir or temp, we need to move it or change download logic
                            # Existing downloader returns path. Let's download to temp then move (download usually doesn't lock like st.audio)
                            # Or better: update downloader to accept output dir?
                            # For now, let's use shutil.move with retry, usually yt-dlp closes file well.

                            temp_video_path = download_video(video_url)
                            status.update(label="下载完成!", state="complete")

                            # Update task name based on downloaded filename
                            filename = os.path.basename(temp_video_path)
                            task_state = task_manager.load_task(task_id)
                            task_state['name'] = os.path.splitext(filename)[0]
                            task_manager.save_task_state(task_id, task_state)

                            final_path = task_manager.update_task_file(task_id, 'original_video', temp_video_path, move=True)

                            st.session_state.processing_state['video_path'] = final_path

                            # Reload session to reflect name change
                            load_task_into_session(task_id)

                            process_video_step(final_path, task_id)
                            st.rerun()
                    except Exception as e:
                        st.error(f"下载失败: {str(e)}")

    # --- TAB 2: Script Processing ---
    with tab2:
        st.header("文案改写与润色")

        # Attempt to load script cache
        if st.session_state.processing_state['video_path'] and not st.session_state.processing_state['podcast_script']:
            script_cache_path = f"{st.session_state.processing_state['video_path']}.script.txt"
            if os.path.exists(script_cache_path):
                with open(script_cache_path, "r", encoding="utf-8") as f:
                    st.session_state.processing_state['podcast_script'] = f.read()
                st.info("✅ 已自动加载本地缓存的播客文案")

        if st.session_state.processing_state['transcript']:
            st.subheader("原始转写内容")
            with st.expander("查看原始文字"):
                st.text_area("Transcript", st.session_state.processing_state['transcript'], height=150, disabled=True)

            st.subheader("播客化改写")

            # If we haven't rewritten yet, or if user wants to re-generate
            # Add a button to force regenerate if script exists
            if st.session_state.processing_state['podcast_script']:
                 if st.button("🔄 重新生成文案"):
                     st.session_state.processing_state['podcast_script'] = None
                     st.rerun()

            if not st.session_state.processing_state['podcast_script']:
                if st.button("🤖 AI 生成播客文案"):
                    if not os.getenv("DEEPSEEK_API_KEY"):
                        st.error("请先在 .env 文件中配置 DEEPSEEK_API_KEY")
                    else:
                        with st.spinner("正在调用 DeepSeek 进行改写..."):
                            try:
                                rewriter = Rewriter(
                                    api_key=os.getenv("DEEPSEEK_API_KEY"),
                                    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                                    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
                                )
                                script = rewriter.rewrite_for_podcast(st.session_state.processing_state['transcript'])
                                st.session_state.processing_state['podcast_script'] = script

                                # Save to Task
                                if st.session_state.current_task_id:
                                    task_manager.update_task_data(st.session_state.current_task_id, 'script_content', script)

                                # Save cache (Legacy support, maybe remove later)
                                if st.session_state.processing_state['video_path']:
                                    script_cache_path = f"{st.session_state.processing_state['video_path']}.script.txt"
                                    with open(script_cache_path, "w", encoding="utf-8") as f:
                                        f.write(script)
                                    logger.info(f"Saved script cache to {script_cache_path}")

                                st.rerun()
                            except Exception as e:
                                st.error(f"改写失败: {str(e)}")

            # Show editor if script exists
            if st.session_state.processing_state['podcast_script']:
                edited_script = st.text_area(
                    "编辑播客文案 (可直接修改)",
                    value=st.session_state.processing_state['podcast_script'],
                    height=300
                )
                st.session_state.processing_state['podcast_script'] = edited_script

                st.info("💡 确认文案无误后，请前往【步骤 3】生成语音。")

        else:
            st.info("请先在【步骤 1】中完成视频处理与转写。")

    # --- TAB 3: Synthesis ---
    with tab3:
        st.header("语音合成与视频生成")

        # Auto-load cached audio if available
        cache_audio_path = os.path.join("temp", "podcast_audio.mp3")
        if not st.session_state.processing_state['podcast_audio'] and os.path.exists(cache_audio_path):
             st.session_state.processing_state['podcast_audio'] = cache_audio_path
             st.info(f"✅ 检测到上次生成的语音，已自动加载。")

        if st.session_state.processing_state['podcast_script']:

            # TTS Generation
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗣️ 生成双人对话语音"):
                    with st.spinner("正在生成对话 (可能需要几分钟)..."):
                        try:
                            # Determine output path based on task
                            if st.session_state.current_task_id:
                                task_dir = task_manager.get_task_dir(st.session_state.current_task_id)
                                output_audio = os.path.join(task_dir, "podcast_audio.mp3")
                            else:
                                ensure_dir("temp")
                                output_audio = os.path.join("temp", "podcast_audio.mp3")

                            # Prepare Configs
                            # Credentials are now handled by VolcService via .env

                            host_conf = {
                                "voice": host_voice,
                                "provider": "volc" if host_provider == "Volcengine (火山引擎)" else "edge",
                                "rate": speech_rate
                            }

                            guest_conf = {
                                "voice": guest_voice,
                                "provider": "volc" if "Volcengine" in guest_provider else "edge",
                                "rate": speech_rate
                            }

                            generate_dialogue_audio(
                                st.session_state.processing_state['podcast_script'],
                                host_config=host_conf,
                                guest_config=guest_conf,
                                output_file=output_audio
                            )

                            if st.session_state.current_task_id:
                                # Update state directly (file is already in place)
                                task_state = task_manager.load_task(st.session_state.current_task_id)
                                task_state['files']['podcast_audio'] = "podcast_audio.mp3"
                                task_manager.save_task_state(st.session_state.current_task_id, task_state)
                                st.session_state.processing_state['podcast_audio'] = output_audio
                            else:
                                st.session_state.processing_state['podcast_audio'] = output_audio

                            st.success("语音生成成功!")
                        except Exception as e:
                            st.error(f"语音生成失败: {str(e)}")

            if st.session_state.processing_state['podcast_audio']:
                st.audio(st.session_state.processing_state['podcast_audio'])

                st.divider()

                # Video Synthesis
                st.subheader("合成最终视频")

                # Allow uploading image here specifically for synthesis if not done in sidebar
                custom_bg = st.file_uploader("上传视频封面/背景图 (覆盖侧边栏设置)", type=["jpg", "png", "jpeg"], key="synthesis_bg")
                final_bg_image = custom_bg if custom_bg else bg_image

                render_engine = st.radio("渲染引擎", ["FFmpeg (快速/简单)", "Remotion (精美动画/慢)"], horizontal=True)

                if st.button("🎬 合成最终视频"):
                    if not final_bg_image:
                        st.warning("⚠️ 未上传背景图，将使用默认黑色背景 (或请在侧边栏上传)")
                        st.error("请上传一张背景图 (JPG/PNG)")
                    else:
                        with st.spinner("正在合成视频 (请耐心等待)..."):
                            try:
                                ensure_dir("output")
                                ensure_dir("temp")

                                # Save background image
                                bg_path = os.path.join("temp", "background_image.jpg")
                                with open(bg_path, "wb") as f:
                                    f.write(final_bg_image.getbuffer())

                                output_video = os.path.join("output", "final_podcast.mp4")
                                audio_path = st.session_state.processing_state['podcast_audio']

                                if render_engine == "FFmpeg (快速/简单)":
                                    create_podcast_video(
                                        bg_path,
                                        audio_path,
                                        output_video,
                                        subtitle_path=audio_path + ".srt"
                                    )
                                else:
                                    # Remotion Render
                                    # Check if JSON exists (generated by TTS)
                                    json_path = audio_path + ".json"
                                    if not os.path.exists(json_path):
                                        st.error("未找到字幕数据 (JSON)，请先重新生成语音。")
                                        st.stop()

                                    render_remotion_video(
                                        audio_path,
                                        bg_path,
                                        json_path,
                                        output_video
                                    )

                                if st.session_state.current_task_id:
                                    # Save final video to task folder
                                    final_video_path = task_manager.update_task_file(st.session_state.current_task_id, 'final_video', output_video, move=False)
                                    st.session_state.processing_state['final_video'] = final_video_path
                                else:
                                    st.session_state.processing_state['final_video'] = output_video

                                st.success("视频合成完成!")
                            except Exception as e:
                                st.error(f"合成失败: {str(e)}\n如果是 Remotion 失败，请检查是否安装了 Node.js 和依赖。")

                if st.session_state.processing_state['final_video']:
                    st.video(st.session_state.processing_state['final_video'])

                    with open(st.session_state.processing_state['final_video'], "rb") as f:
                        st.download_button(
                            "⬇️ 下载成品视频",
                            f,
                            file_name="podcast_video.mp4"
                        )
        else:
             st.info("请先在【步骤 2】中生成播客文案。")

def process_video_step(video_path, task_id=None):
    """Process a video/audio file: extract audio and run speech transcription.

    Handles the initial processing pipeline after a file is uploaded or downloaded:
    1. Detects whether the input is audio or video.
    2. Extracts audio to MP3 format (or copies if already audio).
    3. Runs ASR transcription using the selected provider (DashScope or Volcengine).
    4. Updates the task state and session state with results.

    Args:
        video_path (str): Path to the input video or audio file.
        task_id (str, optional): The current task identifier. If provided,
            extracted audio and transcript are saved to the task directory.
            If None, files are saved to a temporary directory.
    """
    ensure_dir("temp")

    # 1. Extract Audio
    with st.spinner("正在处理音频..."):
        try:
            file_ext = os.path.splitext(video_path)[1].lower()

            # Determine Final Audio Path
            if task_id:
                task_dir = task_manager.get_task_dir(task_id)
                # Use source filename but change extension to .mp3 to avoid TOS collision
                # Get original video filename from state if possible, or derive from video_path
                source_name = os.path.splitext(os.path.basename(video_path))[0]
                audio_filename = f"{source_name}.mp3"
                audio_path = os.path.join(task_dir, audio_filename)
            else:
                # Fallback to temp if no task
                audio_path = os.path.join("temp", f"extracted_audio_{int(time.time())}.mp3")

            if file_ext in ['.mp3', '.wav', '.m4a', '.flac']:
                # It is already an audio file
                # If we are in task mode, we need to copy it to 'audio.mp3' if it isn't already
                if task_id and video_path != audio_path:
                     # Use shutil.copy with retry logic just in case, but usually reading video_path is fine
                     # Wait, video_path is already in task dir as 'original_video.mp3' potentially?
                     # Let's just use ffmpeg to copy/convert to ensure standard MP3 format
                     extract_audio(video_path, audio_path)
                elif not task_id:
                     audio_path = video_path

                st.info(f"检测到音频文件，已准备就绪: {file_ext}")
            else:
                # It is a video file, extract audio DIRECTLY to final destination
                extract_audio(video_path, audio_path)
                # Wait for file handle to be released fully (Windows fix)
                time.sleep(1)

            # Update State
            if task_id:
                # We manually update state because we bypassed update_task_file to avoid locking
                task_state = task_manager.load_task(task_id)
                task_state['files']['audio'] = os.path.basename(audio_path)
                task_manager.save_task_state(task_id, task_state)

            st.session_state.processing_state['audio_path'] = audio_path
        except Exception as e:
            st.error(f"音频处理失败: {str(e)}")
            return

    # 2. Transcribe
    if st.session_state.get('asr_provider') == 'dashscope':
        if not os.getenv("DASHSCOPE_API_KEY"):
            st.warning("⚠️ 未检测到 DASHSCOPE_API_KEY，请在 .env 文件中配置。")
            return
        logger_msg = "正在转写音频 (阿里百炼 FunASR)..."
    else:
        # Volcengine checks are done inside the class/service
        if not os.getenv("VOLC_ACCESS_KEY"):
             st.warning("⚠️ 未检测到 VOLC_ACCESS_KEY，请在 .env 文件中配置。")
             return
        logger_msg = "正在转写音频 (火山引擎 Paraformer)..."

    with st.spinner(logger_msg):
        try:
            transcriber = Transcriber(provider=st.session_state.get('asr_provider', 'dashscope'))
            transcript = transcriber.transcribe(st.session_state.processing_state['audio_path'])
            st.session_state.processing_state['transcript'] = transcript

            if task_id:
                task_manager.update_task_data(task_id, 'transcript_text', transcript)

            st.success("转写完成! 请前往【步骤 2】查看。")
        except Exception as e:
            st.error(f"转写失败: {str(e)}")

@st.cache_resource
def init_static_server():
    """Initialize the local static file server (cached by Streamlit).

    Uses ``@st.cache_resource`` to ensure the server is started only once
    across Streamlit reruns. The server provides HTTP access to local files
    for the Remotion video rendering engine.

    Returns:
        bool: Always returns True after server initialization.
    """
    start_static_server()
    return True

if __name__ == "__main__":
    # Start static server using cache_resource to avoid re-running on reload
    init_static_server()
    main()
