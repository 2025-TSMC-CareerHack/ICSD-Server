import vertexai
from vertexai.generative_models import GenerativeModel

PROJECT_ID = "tsmccareerhack2025-icsd-grp6"  # Replace with your project ID
REGION = "us-central1"
vertexai.init(project=PROJECT_ID, location=REGION)
model = GenerativeModel("gemini-1.5-pro-002")
file1 = open("Transcript1.txt", "r", encoding="utf-8")
Transcript = file1.read()
file2 = open("cmn-Hant-TW.txt", "r", encoding="utf-8")
Knowledge = file2.read()

#@app.post("/translate_to_chinese")
# async def translate_to_chinese(request: Request):
# data = await request.json()
# meeting_text = data.get("text", "")

# if not meeting_text:
#     return JSONResponse(content={"success": False, "message": "沒有會議內容"}, status_code=400)
meeting_text = Transcript

prompt = f"""
你是一個專業的翻譯員，精通繁體中文、英語、日語和德語。
在翻譯時，你會特別注意原文當中是否包含以下列表中的專有名詞，若有，則保留專有名詞不翻譯，再用括號在該專有名詞的後方附上解釋：

```
{Knowledge}
```

現在，你的任務為「請將以下的逐字稿，翻譯成繁體中文」：

```
{meeting_text}
```
"""

print(prompt)

try:
    response = model.generate_content(prompt)
    response = model.generate_content(
        contents=[Knowledge,prompt],
        generation_config={
            #"max_output_tokens": 500,
            "temperature": 0.1
        }
    )
    # markdown_text = response.text if response.text else "摘要生成失敗"
#     return JSONResponse(content={"success": True, "markdown": markdown_text})
    print(response.text)
except Exception as e:
#     return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)
    print(f"Error occur:{e}")

file1.close()
file2.close()