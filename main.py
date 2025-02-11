from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
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



from final_recognizer import final_transcribe
from stream_recognizer import StreamRecognizer

# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# genai.configure(api_key=GEMINI_API_KEY)
PROJECT_ID = os.getenv("PROJECT_ID")
REGION = "us-central1" 
vertexai.init(project=PROJECT_ID,  location=REGION) 
model  =  GenerativeModel(  "gemini-1.5-pro-002"  ) 
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


SAVE_DIR = "recordings"
os.makedirs(SAVE_DIR, exist_ok=True)
UPLOAD_DIR = "upload"
os.makedirs(UPLOAD_DIR, exist_ok=True)

broadcast_clients = []
meetings = {}

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
    recording_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + language
    return JSONResponse(content={"recording_id": recording_id})

@app.websocket("/ws/record/{meeting_id}/{recording_id}")
async def websocket_record(websocket: WebSocket, meeting_id: str, recording_id: str):
    await websocket.accept()
    
    if meeting_id not in meetings:
        await websocket.close()
        return
    
    meetings[meeting_id]["clients"].append(websocket)

    filename = f"{SAVE_DIR}/recording_{recording_id}.wav"
    wav_file = wave.open(filename, "wb")
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(16000)

    # 解析語言代碼
    parts = recording_id.rsplit("_", 1)
    language_code = parts[1] if len(parts) == 2 else "en-US"

    # 會議內部的 `broadcast_clients`
    broadcast_clients = meetings[meeting_id]["clients"]

    # 建立即時辨識器
    loop = asyncio.get_running_loop()
    recognizer = StreamRecognizer(language_code, loop, broadcast_clients)
    
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
                wav_file.writeframes(chunk)
                recognizer.add_audio_data(chunk)
            elif "text" in data:
                if data["text"] == "STOP":
                    break
    except WebSocketDisconnect:
        print(f"客戶端斷開會議 {meeting_id}")
    finally:
        recognizer.stop()
        recognition_thread.join(timeout=2)
        
        wav_file.close()
        print(f"錄音檔案已儲存：{filename}")

        # 使用 V2 進行最終完整辨識
        final_text = await loop.run_in_executor(
            None, 
            final_transcribe, 
            filename, 
            language_code
        )

        # 廣播最終結果只給該會議室的 `clients`
        final_message = f"final:{language_code} {final_text}"
        to_remove = []
        for client in broadcast_clients:
            try:
                await client.send_text(final_message)
            except Exception as e:
                print("廣播最終辨識結果失敗:", e)
                to_remove.append(client)
        for client in to_remove:
            broadcast_clients.remove(client)


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
    data = await request.json()
    token = data.get("credential", "").strip()
    if not token or token == "undefined":
        raise HTTPException(status_code=400, detail="無效的 token：前端未傳送正確的認證資料")
    try:
        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), GOOGLE_CLIENT_ID)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"無效的 token: {str(e)}")
    
    user = {
        "user_id": idinfo.get("sub"),
        "name": idinfo.get("name"),
        "email": idinfo.get("email"),
        "picture": idinfo.get("picture")
    }
    # 將使用者資料儲存於 session 中
    request.session["user"] = user
    return JSONResponse(content={"message": "登入成功", "user": user})

@app.get("/profile")
async def profile(request: Request):
    user = request.session.get("user")
    if user:
        return JSONResponse(content={"profile": user})
    else:
        raise HTTPException(status_code=401, detail="未登入")

@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return JSONResponse(content={"message": "已成功登出"})


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
    uvicorn.run(app, host="localhost", port=8765)
