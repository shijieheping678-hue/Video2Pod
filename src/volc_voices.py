"""Volcengine (ByteDance) TTS voice configuration data.

Defines available voices for the Volcengine TTS engine, including both
BigModel (V3) voices and Standard (V1) voices. Each voice is represented
as a tuple of (voice_id, display_name).

BigModel voices use the V3 streaming API, while Standard voices use
the V1 API. Cloned voices (prefixed with "S_") are routed automatically
to the ICL API.
"""

# Format: (Voice ID, Description)
VOLC_TTS_VOICES = [
    # BigModel Voices (V3) - Male Only (Selected)
    ("zh_male_dayi_saturn_bigtts", "[大模型] 大壹 (视频配音)"),
    ("zh_male_ruyayichen_saturn_bigtts", "[大模型] 儒雅逸辰 (视频配音)"),
    ("zh_male_m191_uranus_bigtts", "[大模型] 云舟 (通用场景)"),
    ("zh_male_taocheng_uranus_bigtts", "[大模型] 小天 (通用场景)"),

    # Standard V1 Voices (Legacy)
    ("BV001_streaming", "通用女声 (BV001 - 免费/默认)"),
    ("BV002_streaming", "通用男声 (BV002 - 免费/默认)"),
    ("BV700_streaming", "甜美解说 (BV700)"),
    ("BV406_streaming", "温柔御姐 (BV406)"),
    ("BV407_streaming", "亲切男声 (BV407)"),
    ("BV005_streaming", "知性姐姐 (BV005)"),
    ("BV004_streaming", "纯正播音 (BV004)"),
    ("BV056_streaming", "小萝莉 (BV056)"),
    ("BV009_streaming", "超级奶爸 (BV009)"),
]
