"""Microsoft Edge TTS voice configuration data.

Defines available Chinese (Mandarin) voices for the Edge TTS engine.
Each voice is represented as a tuple of (voice_id, display_name).

These voices are free to use and require no API key.
"""

# Format: (Short Name, Description)
EDGE_TTS_VOICES = [
    # Chinese (Mainland - Mandarin)
    ("zh-CN-YunyangNeural", "云扬 (男 - 专业新闻/稳重 - 推荐)"),
    ("zh-CN-YunxiNeural", "云希 (男 - 阳光活泼 - 推荐播客)"),
    ("zh-CN-XiaoxiaoNeural", "晓晓 (女 - 温暖亲切 - 推荐)"),
    ("zh-CN-YunjianNeural", "云健 (男 - 体育/激情)"),
    ("zh-CN-XiaoyiNeural", "晓伊 (女 - 卡通/活泼)"),
    ("zh-CN-YunxiaNeural", "云夏 (男 - 卡通/可爱)"),

    # Chinese (Dialects - Fun/Specific)
    ("zh-CN-liaoning-XiaobeiNeural", "晓北 (女 - 东北辽宁话 - 幽默)"),
    ("zh-CN-shaanxi-XiaoniNeural", "晓妮 (女 - 陕西方言)"),
]
