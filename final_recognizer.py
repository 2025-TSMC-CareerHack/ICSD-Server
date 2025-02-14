from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
import os
import wave

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-project-id")


def get_audio_length(filename):
    with wave.open(filename, "rb") as f:
        return f.getnframes() / f.getframerate()



def final_transcribe(filename: str, language_code: str) -> str:
    client = SpeechClient()

    with open(filename, "rb") as f:
        audio_content = f.read()
        
    # 判斷語音長度有沒有超過 30 秒
    audio_length = get_audio_length(filename)
    model = ""
    if audio_length > 10:
        model = "latest_long"
    else:
        model = "latest_short"

    if language_code == "en-US":
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=[language_code],
            model=model,
        )
    else:
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=["en-US", language_code],
            model=model,
        )

    request = cloud_speech.RecognizeRequest(
        recognizer=f"projects/{PROJECT_ID}/locations/global/recognizers/_",
        config=config,
        content=audio_content,
    )

    response = client.recognize(request=request)
    final_text = ""
    for result in response.results:
        final_text += result.alternatives[0].transcript + " "
    return final_text.strip()
