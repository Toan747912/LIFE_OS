---
tags: [dự-án]
cập_nhật: 2026-10-05
---
# Môi trường và chạy

## Môi trường
- Windows, Python 3.11.
- Cần `ffmpeg` và `ffprobe` trong PATH.
- Máy chặn `pip.exe` và `uvicorn.exe` (Application Control): luôn dùng `python -m pip`, `python -m uvicorn`.
- **Luôn chạy từ thư mục gốc dự án.**

## Cài đặt
```powershell
python -m pip install -r requirements.txt
```
`requirements.txt` hiện chỉ có: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `deep-translator>=1.11.4`, `yt-dlp`. Các thư viện code dùng mà file chưa khai:

| Thư viện | Ai dùng |
| --- | --- |
| `edge-tts` | [[Video Dubbing]], [[Backend FastAPI]] `/api/tts`, [[Bilibili Dubbing]] |
| `pydub` | [[Video Dubbing]] (`tts_generator`, `media_mixer`) |
| `faster-whisper` | [[Dynamic Subtitle]], Whisper của [[Bilibili Dubbing]] |
| `argostranslate` | [[Video Dubbing]] (không bắt buộc), [[Backend Flask]] |
| `flask`, `flask-cors`, `gTTS`, `requests` | [[Backend Flask]] |

## Chạy
| Mục đích | Lệnh |
| --- | --- |
| Server chính | `python -m uvicorn app:app --reload --port 8000` |
| Server cho extension | `python vi_sub_server.py` |
| Menu dòng lệnh | `python main.py` |

Hai server cùng cổng 8000 nên không chạy cùng lúc được.

| Trang | Địa chỉ |
| --- | --- |
| Trang chủ lồng tiếng | `http://localhost:8000/` |
| Bilibili Dubbing | `http://localhost:8000/bilibili` |

## Test
```powershell
python -m unittest discover -s modules/bilibili_dubbing/tests -t .
```
132 test tại 2026-10-05. Test không cần mạng; bộ trộn chạy thật nên cần `ffmpeg`. Thiếu `httpx` hoặc `ffmpeg` thì test trọn luồng tự bỏ qua.

Các module cũ chưa có test.

## Extension
Chrome → `chrome://extensions` → bật Developer mode → Load unpacked → chọn `yt-subtitle-extension/`.
