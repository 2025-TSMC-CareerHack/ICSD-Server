from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import wave
import datetime
import os
import asyncio
import threading
from uuid import uuid4


from final_recognizer import final_transcribe
from stream_recognizer import StreamRecognizer

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAVE_DIR = "recordings"
os.makedirs(SAVE_DIR, exist_ok=True)
UPLOAD_DIR = "upload"
os.makedirs(UPLOAD_DIR, exist_ok=True)

broadcast_clients = []
meetings = {}

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8765)
