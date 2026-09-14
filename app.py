import os
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from modules.video_dubbing.service import DubbingConfig, run_dubbing_pipeline
from modules.file_manager import (
    ensure_upload_dir,
    get_unique_filename,
    list_files,
    rename_file,
    delete_file_from_disk,
    UPLOAD_DIR
)

# Khởi tạo ứng dụng FastAPI
app = FastAPI(title="LIFE_OS Video Dubbing API")
templates = Jinja2Templates(directory="templates")

# ─── CORS Middleware ───────────────────────────────────────────────────────────
# Cho phép Chrome Extension từ bất kỳ trang web nào gọi vào backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Trạng thái tiến trình xử lý toàn cục cho video dài
status_state = {"progress": 0, "message": "Chưa xử lý", "is_done": False}

def progress_callback(percent: int, message: str):
    status_state["progress"] = percent
    status_state["message"] = message

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/start-dubbing")
async def start_dubbing(
    background_tasks: BackgroundTasks,
    video_name: str = Form(...),
    subtitle_name: str = Form(...),
    orig_vol: float = Form(0.15),
    dub_vol: float = Form(1.0),
    hard_sub: bool = Form(False),
    enable_dynamic_sub: bool = Form(False)
):
    """
    Nhận tên file video và tên file phụ đề từ người dùng (từ dropdown HTML),
    ghép với UPLOAD_DIR tạo đường dẫn tuyệt đối/tương đối rồi truyền vào DubbingConfig.
    """
    ensure_upload_dir()
    video_path = os.path.join(UPLOAD_DIR, video_name)
    subtitle_path = os.path.join(UPLOAD_DIR, subtitle_name)

    if not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail=f"File video '{video_name}' không tồn tại trong hệ thống!")
    if not os.path.exists(subtitle_path):
        raise HTTPException(status_code=400, detail=f"File phụ đề '{subtitle_name}' không tồn tại trong hệ thống!")

    config = DubbingConfig(
        video_path=video_path,
        subtitle_path=subtitle_path,
        orig_vol=orig_vol,
        dub_vol=dub_vol,
        hard_sub=hard_sub,
        enable_dynamic_sub=enable_dynamic_sub
    )

    status_state["is_done"] = False
    status_state["progress"] = 0
    status_state["message"] = "Đang khởi tạo quy trình lồng tiếng..."

    def background_job():
        try:
            run_dubbing_pipeline(config, progress_callback=progress_callback)
            status_state["is_done"] = True
            status_state["progress"] = 100
            status_state["message"] = "Hoàn tất xử lý video!"
        except Exception as e:
            status_state["message"] = f"Lỗi: {str(e)}"

    background_tasks.add_task(background_job)
    return {"status": "started"}

@app.get("/status")
async def get_status():
    return status_state

@app.get("/download-video")
async def download_video():
    path = "core/output/output_final.mp4"
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename="output_final.mp4")
    return {"error": "Video chưa được tạo"}

# --- Quản lý File CRUD (Tải lên, Liệt kê, Đổi tên, Xóa vật lý trên máy) ---

@app.get("/api/files")
async def api_list_files():
    """Liệt kê toàn bộ file đầu vào trong thư mục máy"""
    return {"files": list_files()}

@app.post("/api/files/upload")
async def api_upload_file(file: UploadFile = File(...)):
    """Tải lên file video/phụ đề với cơ chế chống trùng tên tự động và zero-RAM streaming"""
    ensure_upload_dir()
    safe_name = get_unique_filename(file.filename)
    dest_path = os.path.join(UPLOAD_DIR, safe_name)

    # Dùng stream (shutil.copyfileobj) để tối ưu dung lượng cho video nặng (như video 5 tiếng)
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"success": True, "filename": safe_name, "message": "Tải lên thành công!"}

@app.put("/api/files/rename")
async def api_rename_file(old_name: str = Form(...), new_name: str = Form(...)):
    """Đổi tên file có kiểm tra trùng lặp trên ổ cứng"""
    result = rename_file(old_name, new_name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.delete("/api/files/{filename}")
async def api_delete_file(filename: str):
    """Xóa vĩnh viễn file khỏi ổ cứng máy tính"""
    result = delete_file_from_disk(filename)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result

# ─── Subtitle Translation & TTS API (dùng cho Chrome Extension) ──────────────

from deep_translator import GoogleTranslator

@app.post("/api/translate")
async def translate_text(text: str = Form(...)):
    """
    Nhận text tiếng Anh (hoặc bất kỳ ngôn ngữ nào) qua FormData,
    trả về bản dịch tiếng Việt.

    Request: POST /api/translate
    Body (multipart/form-data): text=<câu cần dịch>
    Response: { "translation": "bản dịch tiếng Việt" }
    """
    if not text or not text.strip():
        return {"translation": ""}
    try:
        translated = GoogleTranslator(source="auto", target="vi").translate(text.strip())
        return {"translation": translated or ""}
    except Exception as e:
        return {"translation": "", "error": str(e)}


# ─── TTS API — dùng edge-tts nếu có cài (pip install edge-tts) ────────────────
# Nếu chưa cài: endpoint vẫn tồn tại nhưng trả lỗi 503 có hướng dẫn.
# Extension dùng Web Speech API làm fallback khi endpoint này báo lỗi.
#
# Để bật giọng đẹp:
#   pip install edge-tts
#   Trong content.js: đặt CONFIG.USE_BACKEND_TTS = true
#
# Giọng hỗ trợ (thay đổi EDGE_TTS_VOICE bên dưới):
#   vi-VN-HoaiMyNeural   — giọng nữ tự nhiên (mặc định)
#   vi-VN-NamMinhNeural  — giọng nam

import tempfile, asyncio
EDGE_TTS_VOICE = "vi-VN-HoaiMyNeural"

try:
    import edge_tts as _edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False

@app.post("/api/tts")
async def text_to_speech(text: str = Form(...)):
    """
    Chuyển văn bản tiếng Việt thành file MP3 (edge-tts).

    Request: POST /api/tts
    Body (multipart/form-data): text=<văn bản tiếng Việt>
    Response: audio/mpeg (MP3 stream)

    Yêu cầu: pip install edge-tts
    """
    if not _EDGE_TTS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="edge-tts chưa được cài. Chạy: pip install edge-tts"
        )
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="text không được rỗng")

    try:
        # Tạo file tạm để ghi MP3
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        communicate = _edge_tts.Communicate(text.strip(), voice=EDGE_TTS_VOICE)
        await communicate.save(tmp_path)

        return FileResponse(
            tmp_path,
            media_type="audio/mpeg",
            filename="tts.mp3",
            background=BackgroundTasks()   # FastAPI tự xóa file sau khi gửi
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS lỗi: {str(e)}")
