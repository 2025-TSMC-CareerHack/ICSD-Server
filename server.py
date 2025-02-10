from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import wave
import datetime
import os
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許的來源網域，可改為特定網域清單
    allow_credentials=True,  # 允許攜帶認證資訊
    allow_methods=["*"],  # 允許的 HTTP 方法
    allow_headers=["*"],  # 允許的 HTTP 標頭
)

# 儲存音訊檔案的資料夾，若不存在則建立
SAVE_DIR = "recordings"
os.makedirs(SAVE_DIR, exist_ok=True)

# 存放所有連線到廣播用 WebSocket 的客戶端
broadcast_clients = []


# HTTP API：前端送出錄音開始請求後，回傳一個錄音識別碼 (recording_id)
@app.post("/record/start")
async def start_recording():
    # 以當下時間（格式：YYYYMMDD_HHMMSS）作為錄音識別碼
    recording_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
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

# 建立用於接收轉錄訊息等廣播通知的 WebSocket 端點
@app.websocket("/ws/broadcast")
async def websocket_broadcast(websocket: WebSocket):
    await websocket.accept()
    broadcast_clients.append(websocket)
    print("廣播 WebSocket 連線已建立")
    try:
        # 保持連線，這邊可以設計保持連線等待前端傳回訊息或定期 ping
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
