from src.voice_cloner import VoiceCloner


def train_my_voice(audio_path, speaker_id):
    print(f"开始训练音色: {speaker_id} ...")

    cloner = VoiceCloner()

    try:
        # 1. 上传
        cloner.upload_audio(audio_path, speaker_id)
        print("上传成功，正在训练中...")

        # 2. 等待结果 (会阻塞直到完成或超时)
        cloner.wait_for_training(speaker_id, timeout=120)

        print(f"训练成功！音色ID: {speaker_id}")
        return True

    except Exception as e:
        print(f"训练失败: {str(e)}")
        return False

if __name__ == "__main__":
      train_my_voice("my.m4a", "S_0VWdKj6T1")