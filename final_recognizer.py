from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
import os

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-project-id")

def final_transcribe(filename: str, language_code: str) -> str:
    client = SpeechClient()

    with open(filename, "rb") as f:
        audio_content = f.read()

    config = cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=[language_code],
        model="long",
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
