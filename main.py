from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import wave
import datetime
import os
import queue
import threading
import asyncio

from speech_recognition import streaming_recognize

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 可依需求調整允許的網域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 錄音檔案儲存目錄
SAVE_DIR = "recordings"
os.makedirs(SAVE_DIR, exist_ok=True)

# 上傳錄音檔存放目錄
UPLOAD_DIR = "upload"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 存放所有連線到廣播 WebSocket 的客戶端
broadcast_clients = []


@app.post("/record/start")
async def start_recording(request: Request):
    # 讀取前端傳來的 JSON 資料，取得 language 欄位
    data = await request.json()
    language = data.get("language", "unknown")
    # 以當下時間 (格式：YYYYMMDD_HHMMSS) 作為錄音識別碼，並將語言代碼附在後面
    recording_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + language
    return JSONResponse(content={"recording_id": recording_id})


@app.websocket("/ws/record/{recording_id}")
async def websocket_record(websocket: WebSocket, recording_id: str):
    await websocket.accept()
    # 建立 WAV 檔案來存放錄音
    filename = f"{SAVE_DIR}/recording_{recording_id}.wav"
    wav_file = wave.open(filename, "wb")
    wav_file.setnchannels(1)    # 單聲道
    wav_file.setsampwidth(2)     # 16-bit PCM
    wav_file.setframerate(16000) # 16kHz
    print(f"開始接收音訊，錄音將儲存於 {filename}")
    
    # 建立音訊佇列，供語音辨識使用
    audio_queue = queue.Queue()
    
    # 從 recording_id 分離出語言代碼 (示範格式："YYYYMMDD_HHMMSS_en-US")
    parts = recording_id.rsplit("_", 1)
    if len(parts) == 2:
        language_code = parts[1]
    else:
        language_code = "en-US"
    
    # 取得目前事件迴圈 (供背景執行緒使用)
    loop = asyncio.get_running_loop()
    
    # 啟動背景執行緒，呼叫 speech to text 函式進行即時辨識，結果會廣播到所有客戶端
    recognition_thread = threading.Thread(
        target=streaming_recognize,
        args=(audio_queue, language_code, loop, broadcast_clients),
        daemon=True,
    )
    recognition_thread.start()
    
    try:
        while True:
            data = await websocket.receive()
            if "bytes" in data:
                chunk = data["bytes"]
                wav_file.writeframes(chunk)
                # 將音訊資料放入辨識佇列
                audio_queue.put(chunk)
            elif "text" in data:
                if data["text"] == "STOP":
                    # 結束錄音時傳入 None 通知背景辨識結束
                    audio_queue.put(None)
                    break
    except WebSocketDisconnect:
        print("客戶端連線中斷")
    finally:
        wav_file.close()
        print(f"錄音檔案已儲存：{filename}")
        # 將檔案訊息廣播給所有已連線廣播客戶端
        to_remove = []
        for client in broadcast_clients:
            try:
                await client.send_text(f"File saved: {filename}")
            except Exception as e:
                print("廣播失敗:", e)
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


@app.websocket("/ws/broadcast")
async def websocket_broadcast(websocket: WebSocket):
    await websocket.accept()
    broadcast_clients.append(websocket)
    print("廣播 WebSocket 連線已建立")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("廣播客戶端連線中斷")
    finally:
        if websocket in broadcast_clients:
            broadcast_clients.remove(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8765)
