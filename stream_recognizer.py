import queue
import asyncio
from google.cloud import speech
from final_recognizer import final_transcribe
import time
import soundfile as sf
import numpy as np
import requests 
import json
import os
import random

from translate.translate_deepl import *

WHISPER_SERVER_URL = "http://10.121.240.4"
LANGUAGE_MAP = {
    "en-US": "en",
    "cmn-Hant-TW": "zh",
    "ja-JP": "ja",
    "de-DE": "de",
}


async def transcript_audio(wave_path: str, language_code: str) -> str:
    """發送音訊數據到 GPU Whisper 伺服器進行轉錄"""
    # 創建一個臨時音訊檔案
    # with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
    #     temp_file.write(audio_data)
    #     temp_file_path = temp_file.name
    print(f"🔄 載入音訊: {wave_path}")

    try:
        # 設定請求參數
        files = {"file": open(wave_path, "rb")}
        data = {"language": LANGUAGE_MAP.get(language_code, "en")}
        
        print(f"🔄 發送音訊: {wave_path} 進行辨識...")

        # 發送 POST 請求到 Whisper 伺服器
        response = requests.post(f"{WHISPER_SERVER_URL}{random.randint(0, 1)}:876{random.randint(0, 3)}/transcribe", files=files, data=data)
        
        print(f"🔄 Whisper 伺服器回應: {response}")

        if response.status_code == 200:
            return response.json().get("text", "Transcription failed")
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Exception: {str(e)}"

class StreamRecognizer:
    def __init__(self, language_code: str, loop, broadcast_clients, message_id, name, language, translator):
        self.language_code = language_code
        self.loop = loop
        self.broadcast_clients = broadcast_clients  # 這是會議內部的 clients
        self.audio_queue = queue.Queue()
        self.is_running = True
        self.message_id = message_id
        self.name = name
        self.language = language
        self.full_audio_buffer = []  # 儲存所有音訊數據
        self.last_update_time = time.time()
        self.loop = asyncio.get_event_loop()
        self.translator = translator

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
        
        print(f"廣播訊息: {message}")
        
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
            
    async def broadcast_translate(self, translate: str, is_final: bool):
        """只對當前會議的 clients 廣播轉錄結果"""
        # message = f"temp:{translate}"
        print(translate)
        message = {
            "id": self.message_id,
            "message": translate,
            "name": self.name,
            "language": self.language,
            "status": "temp",
            "label": "translate"
        }
        
        print(f"廣播訊息: {message}")
        
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
        
    # async def broadcast_transcript(self, transcript: str, is_final: bool):
    #     """只對當前會議的 clients 廣播轉錄結果"""
    #     # message = f"temp:{translate}"
    #     print(transcript)
    #     message = {
    #         "id": self.message_id,
    #         "message": transcript,
    #         "name": self.name,
    #         "language": self.language,
    #         "status": "temp",
    #         "label": "transcript"
    #     }
        
    #     # print(f"廣播訊息: {message}")
        
    #     to_remove = []
    #     for client in self.broadcast_clients:
    #         try:
    #             await client.send_json(message)
    #         except Exception as e:
    #             print(f"廣播失敗: {e}")
    #             to_remove.append(client)

    #     # 移除已斷線的客戶端
    #     for client in to_remove:
    #         self.broadcast_clients.remove(client)


    def process_audio(self):
        """處理音訊串流並進行即時辨識，並定期更新翻譯"""
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
                    
                    self.full_audio_buffer.append(chunk)  # 累積音訊數據
                    # yield speech.StreamingRecognizeRequest(audio_content=chunk)

                    # 每 0.5 秒鐘更新一次翻譯
                    if time.time() - self.last_update_time >= 1:
                        self.last_update_time = time.time()
                        self.updateTranslate()
                    
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
            
    def updateTranslate(self):
        """將累積的音訊寫入暫存檔並傳遞給翻譯系統"""
        try:
            if not self.full_audio_buffer:
                print("⚠️ 沒有可用的音訊數據，跳過 updateTranslate")
                return
            
            # 將所有累積的音訊轉換為 NumPy 陣列
            audio_data = np.concatenate([np.frombuffer(chunk, dtype=np.int16) for chunk in self.full_audio_buffer])

            temp_wav_path = "temp_audio.wav"

            # 確保音訊存為 16kHz 16-bit PCM WAV 格式
            sf.write(temp_wav_path, audio_data, samplerate=16000, subtype="PCM_16")
            print(f"🎙️ 更新翻譯，音訊已存入: {temp_wav_path}")

            # 使用 asyncio 讓 updateTranslate 可以在事件迴圈內運行
            asyncio.run_coroutine_threadsafe(
                self.send_audio_to_translation(temp_wav_path),
                self.loop
            )

        except Exception as e:
            print(f"⚠️ 更新翻譯時發生錯誤: {e}")


    async def send_audio_to_translation(self, wav_path):
        """模擬發送音檔到翻譯系統 (這裡你需要替換成你的翻譯 API 呼叫)"""
        print(f"🔄 送出音訊: {wav_path} 進行翻譯...")
        start_time = time.time()
        # 這裡可以加上 HTTP POST 請求到翻譯系統
        # 例如: await send_to_translation_server(wav_path)
        temp_text = await transcript_audio(wav_path, self.language_code)
        # temp_text = await self.loop.run_in_executor(None, transcript_audio, wav_path, self.language_code)
        print("🔄 暫時辨識結果: ", temp_text)
        await self.broadcast_transcript(temp_text, True)
        
        # processed_temp_data = await translate_to_chinese(temp_text)
        print(self.translator.translate_to_chinese, temp_text, self.language_code)
        processed_temp_data = self.translator.translate_to_chinese(
            temp_text, LANGUAGE_MAP.get(self.language_code, "en-US").upper()
        ) if self.language_code != "cmn-Hant-TW" else temp_text

        print(f"🔄 翻譯結果: {processed_temp_data}")
        # processed_temp_data = json.loads(processed_temp_data)
        # processed_temp_translated_text = processed_temp_data["translation"]
        
        # print(f"🔄 暫時翻譯結果: {processed_temp_data}")
        await self.broadcast_translate(processed_temp_data, True)
        
        await seript(processed_temp_data, True)
        print(f"🕒 暫時翻譯花費時間: {time.time() - start_time} 秒")
        

    def add_audio_data(self, audio_chunk):
        """加入音訊資料到佇列"""
        self.audio_queue.put(audio_chunk)

    def stop(self):
        """停止辨識"""
        self.is_running = False
        self.audio_queue.put(None)  # 發送結束訊號
