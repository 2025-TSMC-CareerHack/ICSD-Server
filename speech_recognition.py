import asyncio
from google.cloud import speech

def streaming_recognize(audio_queue, language_code, loop, broadcast_clients):
    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code=language_code,
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True,
    )
    
    def request_generator():
        while True:
            chunk = audio_queue.get()
            if chunk is None:
                break
            yield speech.StreamingRecognizeRequest(audio_content=chunk)
    
    responses = client.streaming_recognize(config=streaming_config, requests=request_generator())
    
    for response in responses:
        if not response.results:
            continue
        result = response.results[0]
        if not result.alternatives:
            continue
        transcript = result.alternatives[0].transcript
        # 將辨識結果透過所有廣播 WebSocket 傳送出去
        for client in broadcast_clients:
            try:
                asyncio.run_coroutine_threadsafe(client.send_text(f'temp:{transcript}'), loop)
            except Exception as e:
                print("廣播轉錄文字失敗:", e)
