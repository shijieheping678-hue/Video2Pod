"""Text-to-speech synthesis module with multi-provider support.

Provides TTS functionality through two engines:
- **Edge TTS**: Free Microsoft Edge neural voices (async).
- **Volcengine**: ByteDance commercial TTS with voice cloning support.

Also handles dialogue audio generation by parsing podcast scripts,
synthesizing individual segments, and stitching them together with
SRT subtitles and Remotion-compatible JSON metadata.
"""

import asyncio
import edge_tts
import requests
import json
import uuid
import os
import re
import datetime
from pydub import AudioSegment
from src.utils import logger, ensure_dir
from src.volc_service import VolcService

def clean_text_for_tts(text):
    """Clean text for TTS input by removing unspeakable characters.

    Strips markdown formatting, bracketed annotations (e.g., "(笑)", "[思考]"),
    and other special characters that could cause TTS errors or unnatural speech.

    Args:
        text (str): Raw text that may contain markdown or annotations.

    Returns:
        str: Cleaned text suitable for TTS synthesis.
    """
    # Remove contents in brackets/parentheses e.g. (笑), [思考]
    text = re.sub(r'[\(\[\{（【].*?[\)\]\}）】]', '', text)

    # Remove markdown bold/italic
    text = text.replace('*', '').replace('_', '')

    # Remove whitespace
    text = text.strip()
    return text

# Edge-TTS Functions
async def generate_audio_edge(text, voice="zh-CN-YunxiNeural", output_file="output.mp3", rate=1.0):
    """Generate audio using Microsoft Edge TTS (free, async).

    Converts text to speech using Edge's neural voice engine with retry logic
    for transient network errors.

    Args:
        text (str): Text content to synthesize.
        voice (str): Edge TTS voice identifier. Defaults to "zh-CN-YunxiNeural".
        output_file (str): Path to save the generated MP3 file. Defaults to "output.mp3".
        rate (float): Speech speed multiplier. 1.0 = normal speed, 1.2 = 20% faster.
            Defaults to 1.0.

    Returns:
        str | None: Path to the output file on success, or None if text is empty
            after cleaning.

    Raises:
        Exception: If all retry attempts fail.
    """
    # Clean text first
    text = clean_text_for_tts(text)
    if not text:
        logger.warning("Empty text after cleaning, skipping Edge-TTS.")
        return None

    # Convert rate float to string percentage (e.g. 1.2 -> "+20%")
    rate_str = f"+{int((rate - 1.0) * 100)}%"
    if rate < 1.0:
        rate_str = f"{int((rate - 1.0) * 100)}%" # e.g. -20%

    logger.info(f"Generating TTS audio (Edge) with voice: {voice}, rate: {rate_str}")

    # Retry logic for Edge-TTS
    max_retries = 3
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate_str)
            await communicate.save(output_file)
            return output_file
        except Exception as e:
            logger.warning(f"Edge-TTS attempt {attempt+1} failed: {str(e)}")
            if attempt == max_retries - 1:
                logger.error(f"Edge-TTS final failure: {str(e)}")
                raise e
            await asyncio.sleep(1) # Wait before retry


# Volcengine TTS Functions
def generate_audio_volc(text, voice_type, output_file, speed_ratio=1.0, **kwargs):
    """Generate audio using Volcengine (ByteDance) TTS service.

    Delegates to VolcService for the actual API call. Credentials are
    read from environment variables by VolcService.

    Args:
        text (str): Text content to synthesize.
        voice_type (str): Volcengine voice identifier (e.g., "BV001_streaming"
            for standard voices, or "S_xxx" for cloned voices).
        output_file (str): Path to save the generated MP3 file.
        speed_ratio (float): Speech speed multiplier. Defaults to 1.0.
        **kwargs: Additional keyword arguments (reserved for future use).

    Returns:
        str | None: Path to the output file on success, or None if text is
            empty/invalid after cleaning.

    Raises:
        Exception: If the Volcengine TTS API call fails.
    """
    # Clean text
    text = clean_text_for_tts(text)
    # Check if text contains valid characters (not just punctuation)
    if not text or not any(c.isalnum() for c in text):
        logger.warning(f"Skipping Volcengine TTS for empty/invalid text: '{text}'")
        return None

    logger.info(f"Generating TTS audio (Volcengine) with voice: {voice_type}, speed: {speed_ratio}")
    try:
        service = VolcService()
        return service.synthesize_speech(text, voice_type, output_file, speed_ratio=speed_ratio)
    except Exception as e:
        logger.error(f"Volcengine TTS failed: {str(e)}")
        raise e

def generate_audio_sync(text, voice, output_file, provider="edge", **kwargs):
    """Synchronous wrapper that routes TTS requests to the correct provider.

    Acts as a unified entry point for TTS generation, dispatching to either
    Edge TTS or Volcengine based on the provider parameter.

    Args:
        text (str): Text content to synthesize.
        voice (str): Voice identifier appropriate for the chosen provider.
        output_file (str): Path to save the generated MP3 file.
        provider (str): TTS engine to use. "edge" for Edge TTS, "volc" for
            Volcengine. Defaults to "edge".
        **kwargs: Additional options passed to the underlying provider.
            Commonly used keys:
            - ``rate`` (float): Speech speed multiplier. Defaults to 1.3.

    Returns:
        str | None: Path to the output file on success, or None if skipped.
    """
    rate = kwargs.get('rate', 1.3)
    if provider == "volc":
        # We don't need to pass appid/token explicitly as VolcService handles it from env
        return generate_audio_volc(text, voice, output_file, speed_ratio=rate)
    else:
        return asyncio.run(generate_audio_edge(text, voice, output_file, rate=rate))

def format_srt_time(ms):
    """Convert milliseconds to SRT timestamp format.

    Args:
        ms (int): Time in milliseconds.

    Returns:
        str: Formatted timestamp string in "HH:MM:SS,mmm" format.

    Examples:
        >>> format_srt_time(3661500)
        '01:01:01,500'
    """
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{int(milliseconds):03d}"

def split_text_smart(text):
    """Split text into sentence-level chunks based on major punctuation.

    Splits on sentence-ending punctuation (。！？；!?;) while preserving
    commas within chunks to maintain natural speech flow and reduce
    unnatural pauses in TTS output.

    Args:
        text (str): Text to split into chunks.

    Returns:
        list[str]: List of text chunks, each ending at a sentence boundary.

    Examples:
        >>> split_text_smart("你好，我是主持人。欢迎收听！")
        ['你好，我是主持人。', '欢迎收听！']
    """
    # Split regex includes the delimiter in the result
    # Removed commas (，,) from the split list, added English punctuation
    parts = re.split(r'([。！？；!?;])', text)

    chunks = []
    current_chunk = ""

    for part in parts:
        current_chunk += part
        # If this part is a major punctuation, end the chunk
        if re.match(r'[。！？；!?;]', part):
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = ""

    # Append remainder
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks

def generate_dialogue_audio(text, host_config, guest_config, output_file):
    """Generate complete dialogue audio from a podcast script.

    Parses a two-person dialogue script (host/guest), synthesizes each line
    using the configured TTS engines, and stitches all segments into a single
    audio file. Also generates SRT subtitles and Remotion-compatible JSON metadata.

    The script format expected is:
        主持人：[content]
        嘉宾：[content]

    Output files generated:
    - ``<output_file>`` — Final stitched MP3 audio.
    - ``<output_file>.srt`` — SRT subtitle file with color-coded roles.
    - ``<output_file>.json`` — JSON metadata for Remotion video rendering.

    Args:
        text (str): The full podcast dialogue script with role prefixes.
        host_config (dict): TTS configuration for the host voice. Expected keys:
            - ``voice`` (str): Voice identifier.
            - ``provider`` (str): "edge" or "volc".
            - ``rate`` (float): Speech speed multiplier.
        guest_config (dict): TTS configuration for the guest voice. Same keys
            as host_config.
        output_file (str): Path for the output MP3 file.

    Returns:
        str: Path to the generated audio file.

    Raises:
        Exception: If no audio segments are successfully generated.
    """
    logger.info("Starting dialogue generation...")

    # Determine segments directory relative to output file to keep tasks isolated
    # e.g., if output_file is tasks/TaskA/podcast.mp3, segments go to tasks/TaskA/temp/segments/
    output_dir = os.path.dirname(output_file)
    segments_dir = os.path.join(output_dir, "temp", "segments")
    ensure_dir(segments_dir)

    # 1. Parse Script
    lines = text.strip().split('\n')

    # Structure: {'file': path, 'content': text, 'role': role}
    valid_segments = []

    global_seg_index = 0

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        role = "host" # Default
        content = line

        # Check for role prefixes
        if line.startswith("主持人：") or line.startswith("主持人:"):
            role = "host"
            content = re.sub(r"^主持人[:：]", "", line).strip()
        elif line.startswith("嘉宾：") or line.startswith("嘉宾:"):
            role = "guest"
            content = re.sub(r"^嘉宾[:：]", "", line).strip()

        if not content:
            continue

        # Split content into smaller chunks for subtitles
        sub_chunks = split_text_smart(content)
        if not sub_chunks:
            sub_chunks = [content]

        config = host_config if role == "host" else guest_config

        for j, chunk in enumerate(sub_chunks):
            # Save segments to task-specific temp dir
            seg_file = os.path.join(segments_dir, f"seg_{global_seg_index}_{role}.mp3")
            global_seg_index += 1

            # Get rate from config (added in app.py)
            rate = config.get('rate', 1.3)

            try:
                generate_audio_sync(
                    chunk,
                    config['voice'],
                    seg_file,
                    provider=config['provider'],
                    appid=config.get('appid'),
                    token=config.get('token'),
                    rate=rate
                )
                valid_segments.append({
                    'file': seg_file,
                    'content': chunk,
                    'role': role
                })
            except Exception as e:
                logger.error(f"Failed to generate segment {i}-{j}: {e}")
                continue

    # 3. Stitch Audio and Generate SRT
    if not valid_segments:
        raise Exception("No audio segments generated.")

    logger.info(f"Stitching {len(valid_segments)} segments...")
    final_audio = AudioSegment.empty()

    srt_content = ""
    current_time_ms = 0
    # Smaller pause between chunks of the same sentence?
    # No, we split by punctuation, so a small pause is natural.
    pause_duration = 300 # ms

    for i, seg in enumerate(valid_segments):
        # Load audio
        segment_audio = AudioSegment.from_mp3(seg['file'])
        duration = len(segment_audio)

        # Add to final audio
        final_audio += segment_audio

        # Add pause only if it's the end of a sentence or just a comma?
        # For simplicity, add pause everywhere.
        # 300ms is good for commas, maybe too long for some flows but safe.
        final_audio += AudioSegment.silent(duration=pause_duration)

        # Build SRT entry
        start_time_str = format_srt_time(current_time_ms)
        end_time_str = format_srt_time(current_time_ms + duration)

        # Add color based on role
        # Host: yellow (#FFD700), Guest: cyan (#00FFFF)
        color = "#FFD700" if seg['role'] == "host" else "#00FFFF"
        role_label = "主持人" if seg['role'] == "host" else "嘉宾"

        # We can omit role label in subtitles if color distinguishes them,
        # but keeping it is safer for clarity.
        # To make it cleaner: remove role label from text, just use color?
        # User asked for "按照说什么展示什么". Let's keep it simple.

        srt_content += f"{i+1}\n"
        srt_content += f"{start_time_str} --> {end_time_str}\n"
        srt_content += f"<font color=\"{color}\">{seg['content']}</font>\n\n"

        current_time_ms += duration + pause_duration

    # Export MP3
    final_audio.export(output_file, format="mp3")
    logger.info(f"Dialogue audio saved to {output_file}")

    # Export SRT
    srt_output_file = output_file + ".srt"
    with open(srt_output_file, "w", encoding="utf-8") as f:
        f.write(srt_content)
    logger.info(f"SRT subtitles saved to {srt_output_file}")

    # Export JSON for Remotion
    json_output_file = output_file + ".json"
    remotion_captions = []

    # Re-calculate timestamps for JSON structure to be consistent
    # (We could have done this in the loop above, but separating for clarity)
    curr_ms_json = 0
    for seg in valid_segments:
        seg_dur = len(AudioSegment.from_mp3(seg['file']))
        remotion_captions.append({
            "start": curr_ms_json,
            "end": curr_ms_json + seg_dur,
            "content": seg['content'],
            "role": seg['role']
        })
        curr_ms_json += seg_dur + pause_duration

    with open(json_output_file, "w", encoding="utf-8") as f:
        json.dump({
            "captions": remotion_captions,
            "durationInSeconds": curr_ms_json / 1000
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"Remotion JSON saved to {json_output_file}")

    return output_file
