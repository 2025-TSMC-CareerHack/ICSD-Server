import os
from mistralai import Mistral

def fix_transcript(transcript, model = 'mistral-large-latest'):
    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        raise ValueError("請先設定環境變數 MISTRAL_API_KEY")
    
    # 指定要使用的模型，此處以 'mistral-large-latest' 為例
    # model = 'mistral-large-latest'
    
    # 初始化 Mistral 用戶端
    client = Mistral(api_key=api_key)
    
    messages = [
        {
            'role': 'user',
            'content': f"""以下是一個從半導體公司會議中，語音轉文字出來的辨識結果，但是其中有一點誤差，
    請依照前後文判斷哪裡可能有誤差並輸出修正後的結果，不要輸出額外文字，如果不需要更改就直接輸出原本的字串，且請特別注意這幾個專有名詞，有可能會被辨識成讀音相似的詞「DDR Ratio、EC、ECS、ECCP、ECN、Emergency stop、Alignment mark、ALP、STB、STK、Route、Scrap、Sorter、Split、大夜、小夜、日班、光罩、DP 、SGP、ETP、Cloud Run、Cloud Function、BigQuery、Pub/Sub、Cloud SQL、Artifact Registry、Cloud Storage、GKE、Vertex AI」：
            \n
                    辨識結果：{transcript}"""
        }
    ]
    
    chat_response = client.chat.complete(
        model=model,
        messages=messages
    )
    
    print(chat_response)
    
    return chat_response.choices[0].message.content

LANGUAGE_CODE = {
    "zh": "繁體中文",
    "en": "英文",
    "ja": "日文",
    "de": "德文"
}


def translate_to_chinese(message, model = 'mistral-large-latest', language_code = 'zh'):
    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        raise ValueError("請先設定環境變數 MISTRAL_API_KEY")
    
    # 指定要使用的模型，此處以 'mistral-large-latest' 為例
    # model = 'mistral-large-latest'
    
    # 初始化 Mistral 用戶端
    client = Mistral(api_key=api_key)
    
    file2 = open("./translate/cmn-Hant-TW.txt", "r", encoding="utf-8")
    Knowledge = file2.read()
    
    prompt = f"""
你是一個專業的翻譯員，精通繁體中文、英語、日語和德語。
在翻譯時，你首先會將那些可能被識別錯誤的專有名詞或是特殊發音，並修正成正確的文字。
接下來你會特別注意原文當中是否包含以下列表中的專有名詞，若有，則保留專有名詞不翻譯，再用括號在該專有名詞的後方附上解釋，如果是人名也同樣不翻譯：

```
{Knowledge}
```

現在，你的任務為「請將以下的逐字稿，翻譯成繁體中文」：

```
{message}
```

最後，請輸出一個純 JSON 格式的回應，不要含有其他字元，也不要包含區塊引言的格式，只輸出內文，並包含修正後的原文以及翻譯後的結果，如：
{{"original": "原文","translation": "翻譯"}}
"""
    
    messages = [
        {
            'role': 'user',
            'content': prompt
        }
    ]
    
    chat_response = client.chat.complete(
        model=model,
        messages=messages
    )
    
    print(chat_response)
    
    return chat_response.choices[0].message.content

def main():
    # 設定 API 金鑰
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("請先設定環境變數 MISTRAL_API_KEY")
    
    # 初始化 Mistral 客戶端
    client = Mistral(api_key=api_key)
    
    # 定義要使用的模型
    model = "mistral-large-latest"
    
    # 輸入語音轉文字結果，並提供指令要求模型進行修正
    user_input = """
    以下是一個從半導體公司會議中，語音轉文字出來的辨識結果，但是其中有一點誤差，
    請依照前後文判斷哪裡可能有誤差並輸出修正後的結果，不需要輸出額外解釋，且請特別注意這幾個專有名詞，有可能會被辨識成讀音相似的詞「DDR Ratio、EC、ECS、ECCP、ECN、Emergency stop、Alignment mark、ALP、STB、STK、Route、Scrap、Sorter、Split、大夜、小夜、日班、光罩、DP 、SGP、ETP、Cloud Run、Cloud Function、BigQuery、Pub/Sub、Cloud SQL、Artifact Registry、Cloud Storage、GKE、Vertex AI」：
    
    辨識結果：好的這件事技術上沒問題但我需要回去和我老板討論一下因為這屬於架構上的change我這邊需要新增Co方選來抓漏的資料EQ那邊也需要新增Table欄位才行
    """
    
    # 呼叫聊天完成 API
    response = client.chat.complete(
        model=model,
        messages=[{"role": "user", "content": user_input}]
    )
    
    # 取得模型回應並輸出
    corrected_text = response.choices[0].message.content
    print(corrected_text)

if __name__ == "__main__":
    main()
