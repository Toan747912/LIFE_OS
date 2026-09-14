"""
CORS Configuration snippet cho FastAPI app.py
Chèn đoạn này vào app.py NGAY SAU khi khởi tạo app = FastAPI(...)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ============================================================
# CORS Middleware — BẮT BUỘC để Chrome Extension từ youtube.com
# có thể gọi về backend 127.0.0.1:8000
# ============================================================
app.add_middleware(
    CORSMiddleware,
    # Chỉ cho phép request từ YouTube (không dùng "*" vì có credentials)
    allow_origins=[
        "https://www.youtube.com",
        "https://youtube.com",
    ],
    allow_credentials=False,   # Extension không gửi cookie, để False là đủ
    allow_methods=["*"],        # Cho phép GET, POST, OPTIONS, ...
    allow_headers=["*"],        # Cho phép mọi header (kể cả Content-Type)
)

# ============================================================
# Ví dụ endpoint /api/translate
# Điều chỉnh logic dịch theo thư viện bạn đang dùng
# (deep-translator, argostranslate, googletrans, v.v.)
# ============================================================
from fastapi import Form

@app.post("/api/translate")
async def translate(text: str = Form(...)):
    """
    Nhận text tiếng Anh qua FormData, trả về JSON với bản dịch tiếng Việt.

    Request body (multipart/form-data):
        text: str — câu tiếng Anh cần dịch

    Response JSON:
        { "translation": "bản dịch tiếng Việt" }
    """

    # --- Thay thế đoạn này bằng thư viện dịch thực tế của bạn ---
    # Ví dụ với deep-translator:
    #   from deep_translator import GoogleTranslator
    #   translated = GoogleTranslator(source="en", target="vi").translate(text)

    # Placeholder — xóa và thay bằng logic thật:
    translated = f"[VI] {text}"
    # ------------------------------------------------------------

    return {"translation": translated}
