from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import wave
import datetime
import os
import asyncio
import threading
from uuid import uuid4
import vertexai
from  vertexai.generative_models  import  GenerativeModel 
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from starlette.middleware.sessions import SessionMiddleware
import uuid
import json
from urllib.parse import parse_qs
from starlette.responses import RedirectResponse
import requests

import whisper
import soundfile as sf
import numpy as np


from final_recognizer import final_transcribe
from stream_recognizer import StreamRecognizer
from mongodb_atlas import *
from mistral import *

# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# genai.configure(api_key=GEMINI_API_KEY)
PROJECT_ID = os.getenv("PROJECT_ID")
REGION = "us-central1" 
vertexai.init(project=PROJECT_ID,  location=REGION) 
model  =  GenerativeModel(  "gemini-1.5-pro-002"  ) 
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

# MODEL_NAME = "large"
# print("🔄 加載 Whisper 模型...")
# whisper_model = whisper.load_model(MODEL_NAME)
# print("✅ Whisper 模型加載完成！")


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "https://koying.asuscomm.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="none", https_only=True)

mongo_db = None
db = None
session_collection = None


SAVE_DIR = "recordings"
os.makedirs(SAVE_DIR, exist_ok=True)
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
TRANS_DIR = "translates"
os.makedirs(SAVE_DIR, exist_ok=True)
UPLOAD_DIR = "upload"
os.makedirs(UPLOAD_DIR, exist_ok=True)

broadcast_clients = []
meetings = {}
global message_id

@app.post("/summarize")
async def summarize_meeting(request: Request):
    data = await request.json()
    meeting_text = data.get("text", "")

    if not meeting_text:
        return JSONResponse(content={"success": False, "message": "沒有會議內容"}, status_code=400)

    prompt = f"""
    你是一個專業的筆記整理助理，請根據以下的逐字稿，撰寫中文為主的摘要並以 Markdown 格式輸出：

    ```
    {meeting_text}
    ```

    ## 格式要求：
    - 使用 **標題** 來區分不同議題
    - 以 **條列清單** 方式整理重點
    - 重要資訊請用 **加粗**
    """
    
    print(prompt)

    try:
        response = model.generate_content(prompt)
        markdown_text = response.text if response.text else "摘要生成失敗"

        return JSONResponse(content={"success": True, "markdown": markdown_text})
    except Exception as e:
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

@app.post("/create")
async def create_meeting():
    meeting_id = str(uuid4())[:8]  # 生成簡短的 8 碼會議 ID
    meetings[meeting_id] = {
        "recordings": [],
        "clients": []
    }
    return JSONResponse(content={"meeting_id": meeting_id})

@app.post("/record/start")
async def start_recording(request: Request):
    data = await request.json()
    language = data.get("language", "unknown")
    recording_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] + "_" + language
    return JSONResponse(content={"recording_id": recording_id})

@app.get("/transcript_log")
async def get_log(meeting_id: str):
    try:
        with open(f"{LOG_DIR}/{meeting_id}.json", "r") as f:
            logs = f.readlines()
        return JSONResponse(content=logs)
    except FileNotFoundError:
        return JSONResponse(content={})
    
@app.get("/translate_log")
async def get_log(meeting_id: str):
    try:
        with open(f"{TRANS_DIR}/{meeting_id}.json", "r") as f:
            logs = f.readlines()
        return JSONResponse(content=logs)
    except FileNotFoundError:
        return JSONResponse(content={})

import requests
import json
import tempfile
import os

WHISPER_SERVER_URL = "http://10.121.240.40:8765/transcribe"
LANGUAGE_MAP = {
    "en-US": "en",
    "cmn-Hant-TW": "zh",
    "ja-JP": "ja",
    "de-DE": "de",
}

def transcript_audio(wave_path: str, language_code: str) -> str:
    """發送音訊數據到 GPU Whisper 伺服器進行轉錄"""
    # 創建一個臨時音訊檔案
    # with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
    #     temp_file.write(audio_data)
    #     temp_file_path = temp_file.name

    try:
        # 設定請求參數
        files = {"file": open(wave_path, "rb")}
        data = {"language": LANGUAGE_MAP.get(language_code, "en")}

        # 發送 POST 請求到 Whisper 伺服器
        response = requests.post(WHISPER_SERVER_URL, files=files, data=data)

        if response.status_code == 200:
            return response.json().get("text", "Transcription failed")
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Exception: {str(e)}"
    # finally:
        # 移除臨時音訊檔案
        # os.remove(temp_file_path)


@app.websocket("/ws/record/{meeting_id}/{recording_id}")
async def websocket_record(websocket: WebSocket, meeting_id: str, recording_id: str, session_id: str):
    global message_id
    await websocket.accept()
    
    print(f"🔗 WebSocket 連線已建立: 會議 {meeting_id}, 錄音 ID {recording_id}")
    
    if not session_id:
        await websocket.close()
        return
    user = find_one(sessions_collection, {"session_id": session_id})
    name = user["name"] if user else "Unknown"


    # 確保會議 ID 存在
    if meeting_id not in meetings:
        meetings[meeting_id] = {"clients": []}

    # 創建音訊存檔
    os.makedirs(f"{SAVE_DIR}/{meeting_id}", exist_ok=True)
    filename = f"{SAVE_DIR}/{meeting_id}/{recording_id}.wav"
    wav_file = wave.open(filename, "wb")
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(16000)

    # 解析語言代碼
    parts = recording_id.rsplit("_", 1)
    language_code = parts[1] if len(parts) == 2 else "en"
    language_map = {
        'en-US': 'English',
        'cmn-Hant-TW': 'Chinese',
        'ja-JP': 'Japanese',
        'de-DE': 'Deutsch'
    }
    language = language_map.get(language_code, "Unknown")

    # 會議內部的 `broadcast_clients`
    broadcast_clients = meetings[meeting_id]["clients"]

    # 音訊緩存
    audio_buffer = []
    
    # 建立即時辨識器
    loop = asyncio.get_running_loop()
    message_id += 1
    recognizer = StreamRecognizer(language_code, loop, broadcast_clients, message_id, name, language)
    
    # 在背景執行緒中啟動即時辨識
    recognition_thread = threading.Thread(
        target=recognizer.process_audio,
        daemon=True
    )
    recognition_thread.start()

    try:
        while True:
            data = await websocket.receive()

            if "bytes" in data:
                chunk = data["bytes"]
                audio_buffer.append(np.frombuffer(chunk, dtype=np.int16))
                recognizer.add_audio_data(chunk) 
                wav_file.writeframes(chunk)
            
            elif "text" in data and data["text"] == "STOP":
                print("🛑 收到 STOP 訊號，開始轉錄語音...")
                break

    except WebSocketDisconnect:
        print(f"⚠️ 客戶端斷開連線 (會議 {meeting_id})")

    finally:
        recognizer.stop()
        recognition_thread.join(timeout=5)  # 最多等待 5 秒確保音訊處理完成
        print("✅ 音訊處理已完成")
        wav_file.close()
        print(f"🎙️ 錄音檔案已儲存: {filename}")

        # 確保音訊數據處理完畢
        if len(audio_buffer) > 0:
            # audio_data = np.concatenate(audio_buffer, axis=0).astype(np.float32) / 32768.0  # 轉換成 float32
            # print("🎤 轉錄音訊中...")
            
            if not audio_buffer:
                print("⚠️ 音訊緩衝區為空，無法轉錄")
                return
            
            # 2️⃣ **將音訊緩衝區轉換成 NumPy 陣列**
            audio_data = np.concatenate([np.frombuffer(chunk, dtype=np.int16) for chunk in audio_buffer])
            
            # 3️⃣ **確保音訊數據正確並寫入 WAV 檔案**
            wav_path = f"{filename}.wav"
            sf.write(wav_path, audio_data, samplerate=16000, subtype="PCM_16")
            print(f"🎙️ 音訊檔案已儲存：{wav_path}")
            
            final_text = await loop.run_in_executor(None, transcript_audio, wav_path, language_code)
            print("🔍 原始辨識結果:", final_text)

            # 使用 Whisper 進行語音轉錄
            # result = whisper_model.transcribe(audio_data, language=language_map.get(language_code), fp16=True)
            # result = transcript_audio(audio_data, language_code)
            # print(result)
            # final_text = result["text"]
            # print("🔍 原始辨識結果:", final_text)
        
            to_remove = []
            async def broadcast_message(message):
                for client in broadcast_clients:
                    try:
                        await client.send_json(message)
                    except Exception as e:
                        print("⚠️ 廣播即時辨識結果失敗:", e)
                        to_remove.append(client)
            print("🔍 原始辨識結果:", final_text)
            
            final_message = {
                "id": message_id,
                "message": final_text,
                "name": name,
                "language": language,
                "status": "temp",
                "label": "transcript"
            }
            
            await broadcast_message(final_message)
            
            processed_data = await loop.run_in_executor(None, translate_to_chinese, final_text)
            # make processed_data into json
            print("結果:", processed_data, type(processed_data))
            processed_data = json.loads(processed_data)
            print("結果:", processed_data, type(processed_data))
            optimized_text = processed_data["original"]
            translated_text = processed_data["translation"]
            
            
            print("🔍 修正後辨識結果:", optimized_text)

            # 廣播最終結果
            optimized_message = {
                "id": message_id,
                "message": optimized_text,
                "name": name,
                "language": language,
                "status": "final",
                "label": "transcript"
            }
            await broadcast_message(optimized_message)
            
            translated_message = {
                "id": message_id,
                "message": translated_text,
                "name": name,
                "language": language,
                "status": "final",
                "label": "translate"
            }
            await broadcast_message(translated_message)
                
            
            print("🔍 翻譯結果:", translated_message)
            

            # 儲存會議記錄
            with open(f"{LOG_DIR}/{meeting_id}.json", "a", encoding='utf-8') as f:
                json.dump(optimized_message, f, ensure_ascii=False)
                f.write("\n")  # 確保每條記錄換行
                
            with open(f"{TRANS_DIR}/{meeting_id}.json", "a", encoding='utf-8') as f:
                json.dump(translated_message, f, ensure_ascii=False)
                f.write("\n")
            
            
            for client in to_remove:
                broadcast_clients.remove(client)

            print("🔴 WebSocket 連線已關閉")

@app.post("/record/{recording_id}/upload")
async def upload_recording(recording_id: str, file: UploadFile = File(...)):
    upload_filename = f"{UPLOAD_DIR}/upload_recording_{recording_id}.wav"
    content = await file.read()
    with open(upload_filename, "wb") as f:
        f.write(content)
    return JSONResponse(content={"message": "File uploaded successfully", "filename": upload_filename})

@app.websocket("/ws/broadcast/{meeting_id}")
async def websocket_broadcast(websocket: WebSocket, meeting_id: str):
    await websocket.accept()
    
    if meeting_id not in meetings:
        await websocket.close()
        return

    meetings[meeting_id]["clients"].append(websocket)
    print(f"廣播 WebSocket 連線已建立 (會議 {meeting_id})")

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print(f"廣播客戶端斷開連線 (會議 {meeting_id})")
    finally:
        meetings[meeting_id]["clients"].remove(websocket)

@app.post("/auth/google")
async def google_auth(request: Request):
    try:
        print("🔍 收到請求: /auth/google")
        print(f"🔍 Headers: {request.headers}")

        # 嘗試解析 JSON 或 x-www-form-urlencoded
        raw_body = await request.body()
        body_str = raw_body.decode()
        print(f"🔍 Raw Body: {body_str}")

        # 嘗試解析 JSON
        try:
            data = json.loads(body_str)
        except json.JSONDecodeError:
            # 若 JSON 解析失敗，則嘗試解析 x-www-form-urlencoded
            data = parse_qs(body_str)
            print(f"🔍 Parsed Form Data: {data}")

            # 轉換為標準 Python 字典
            data = {k: v[0] for k, v in data.items()}

        token = data.get("credential", "").strip()
        if not token or token == "undefined":
            raise HTTPException(status_code=400, detail="❌ 無效的 token：前端未傳送正確的認證資料")

        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_CLIENT_ID)

        session_id = str(uuid.uuid4())
        user = {
            "session_id": session_id,
            "user_id": idinfo.get("sub"),
            "name": idinfo.get("name"),
            "email": idinfo.get("email"),
            "picture": idinfo.get("picture"),
        }

        print(f"✅ 驗證成功，使用者資訊: {user}")
        insert_one(sessions_collection, user)

        host = request.url.hostname
        is_local = host in ["localhost", "127.0.0.1"]

        # 根據 `host` 判斷要跳轉的 URL
        redirect_url = "http://localhost:48764/" if is_local else "https://koying.asuscomm.com/TSMC2025/"

        print(f"🔄 重導向至: {redirect_url}")
        response =  RedirectResponse(url=redirect_url, status_code=303)
        response.set_cookie(key="session_id", value=session_id)
        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"無效的 token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"伺服器錯誤: {str(e)}")



@app.get("/profile")
async def profile(request: Request, session_id: str):
    print(session_id)
    if session_id == "0" or not session_id:
        return JSONResponse(content={"message": "找不到使用者"})
    user = find_one(sessions_collection, {"session_id": session_id})
    if not user:
        JSONResponse(content={"message": "找不到使用者"})
    user["_id"] = str(user["_id"])
    print(user)
    return JSONResponse(content={"profile": user})

@app.post("/logout")
async def logout(request: Request, session_id: str):
    print(session_id)
    if not session_id:
        return JSONResponse(content={"message": "找不到使用者"})
    user = find_one(sessions_collection, {"session_id": session_id})
    print("delete:", user)
    if user:
        delete_one(sessions_collection, {"session_id": session_id})
    
    request.session.clear()
    
    return JSONResponse(content={"message": "已成功登出"})

@app.get("/proxy-image")
async def proxy_image(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    return Response(content=response.content, media_type="image/jpeg")


@app.get("/")
async def root():
    """
    讀取並回傳 index.html 當作首頁，
    可在實際環境下使用 StaticFiles 模組來處理靜態資源。
    """
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except Exception as e:
        return HTMLResponse(content="<h1>載入頁面失敗</h1>", status_code=500)

if __name__ == "__main__":
    import uvicorn
    message_id = 0
    mongo_db = connect_to_mongodb()
    db = mongo_db["database"]
    sessions_collection = db["sessions"]
    uvicorn.run(app, host="0.0.0.0", port=8765)
