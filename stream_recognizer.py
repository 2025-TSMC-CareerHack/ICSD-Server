import queue
import asyncio
from google.cloud import speech

class StreamRecognizer:
    def __init__(self, language_code: str, loop, broadcast_clients, message_id, name, language):
        self.language_code = language_code
        self.loop = loop
        self.broadcast_clients = broadcast_clients  # 這是會議內部的 clients
        self.audio_queue = queue.Queue()
        self.is_running = True
        self.message_id = message_id
        self.name = name
        self.language = language

    async def broadcast_transcript(self, transcript: str, is_final: bool):
        """只對當前會議的 clients 廣播轉錄結果"""
        # message = f"temp:{transcript}"
        print(transcript)
        message = {
            "id": self.message_id,
            "message": transcript,
            "name": self.name,
            "language": self.language,
            "status": "temp",
            "label": "transcript"
        }
        
        # print(f"廣播訊息: {message}")
        
        to_remove = []
        for client in self.broadcast_clients:
            try:
                await client.send_json(message)
            except Exception as e:
                print(f"廣播失敗: {e}")
                to_remove.append(client)

        # 移除已斷線的客戶端
        for client in to_remove:
            self.broadcast_clients.remove(client)


    def process_audio(self):
        """處理音訊串流並進行即時辨識"""
        client = speech.SpeechClient()
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=self.language_code,
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        def request_generator():
            while self.is_running:
                try:
                    chunk = self.audio_queue.get(timeout=1)
                    if chunk is None:  # 結束訊號
                        break
                    yield speech.StreamingRecognizeRequest(audio_content=chunk)
                except queue.Empty:
                    continue

        try:
            responses = client.streaming_recognize(
                config=streaming_config,
                requests=request_generator(),
            )

            for response in responses:
                if not response.results:
                    continue

                result = response.results[0]
                if not result.alternatives:
                    continue

                transcript = result.alternatives[0].transcript

                # 使用 run_coroutine_threadsafe 在事件迴圈中執行廣播
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_transcript(transcript, result.is_final),
                    self.loop
                )

        except Exception as e:
            print(f"串流辨識發生錯誤: {e}")

    def add_audio_data(self, audio_chunk):
        """加入音訊資料到佇列"""
        self.audio_queue.put(audio_chunk)

    def stop(self):
        """停止辨識"""
        self.is_running = False
        self.audio_queue.put(None)  # 發送結束訊號
