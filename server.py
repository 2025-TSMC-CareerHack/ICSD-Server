from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import wave
import datetime
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 可依需求調整允許的網域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 儲存錄音檔案的資料夾，若不存在則建立
SAVE_DIR = "recordings"
os.makedirs(SAVE_DIR, exist_ok=True)

# 上傳錄音檔存放目錄
UPLOAD_DIR = "upload"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 存放所有連線到廣播用 WebSocket 的客戶端
broadcast_clients = []


# HTTP API：前端送出錄音開始請求後，回傳一個錄音識別碼 (recording_id)
@app.post("/record/start")
async def start_recording(request: Request):
    # 讀取前端傳來的 JSON 資料，取得 language 欄位
    data = await request.json()
    language = data.get("language", "unknown")
    # 使用當下時間(YYYYMMDD_HHMMSS)作為錄音識別碼，並將語言代碼附加在後
    recording_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + language
    return JSONResponse(content={"recording_id": recording_id})


# WebSocket API：依據前端傳入的 recording_id 建立 WebSocket 連線，
# 客戶端送來的二進位資料即為音訊，送出文字 "STOP" 表示結束錄音，
# 結束錄音後向所有廣播客戶端發送檔名訊息
@app.websocket("/ws/record/{recording_id}")
async def websocket_record(websocket: WebSocket, recording_id: str):
    await websocket.accept()
    # 根據識別碼建立 WAV 檔案
    filename = f"{SAVE_DIR}/recording_{recording_id}.wav"
    wav_file = wave.open(filename, "wb")
    wav_file.setnchannels(1)    # 單聲道
    wav_file.setsampwidth(2)     # 16-bit PCM
    wav_file.setframerate(16000) # 16kHz
    print(f"開始接收音訊，將儲存於 {filename}")
    try:
        while True:
            data = await websocket.receive()
            if "bytes" in data:
                wav_file.writeframes(data["bytes"])
            elif "text" in data:
                if data["text"] == "STOP":
                    break
    except WebSocketDisconnect:
        print("客戶端連線中斷")
    finally:
        wav_file.close()
        print(f"音訊檔案已儲存：{filename}")
        # 廣播檔名訊息到所有已連線的廣播客戶端
        to_remove = []
        for client in broadcast_clients:
            try:
                await client.send_text(filename)
            except Exception as e:
                print("廣播失敗:", e)
                to_remove.append(client)
        # 清除已斷線的客戶端
        for client in to_remove:
            broadcast_clients.remove(client)


# 新增 HTTP API：上傳前端錄製好的音訊檔
@app.post("/record/{recording_id}/upload")
async def upload_recording(recording_id: str, file: UploadFile = File(...)):
    # 使用 recording_id 產生一組檔案名稱，存放至 UPLOAD_DIR 資料夾中
    upload_filename = f"{UPLOAD_DIR}/upload_recording_{recording_id}.wav"
    content = await file.read()
    with open(upload_filename, "wb") as f:
        f.write(content)
    return JSONResponse(content={"message": "File uploaded successfully", "filename": upload_filename})


# 建立用於接收轉錄訊息等廣播通知的 WebSocket 端點
@app.websocket("/ws/broadcast")
async def websocket_broadcast(websocket: WebSocket):
    await websocket.accept()
    broadcast_clients.append(websocket)
    print("廣播 WebSocket 連線已建立")
    try:
        # 保持連線，這邊可根據需求實作心跳機制
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
