"""Các lựa chọn mặc định của người dùng, lưu trong bảng `settings`."""
from __future__ import annotations

from typing import Any, Dict

from modules.bilibili_dubbing.config import BilibiliSettings
from modules.bilibili_dubbing.domain.errors import InvalidRequest
from modules.bilibili_dubbing.storage.repositories import SettingsRepository

VOICES = ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural")
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")


class AppSettingsService:
    def __init__(self, repo: SettingsRepository, settings: BilibiliSettings):
        self._repo = repo
        self._settings = settings

    def get(self) -> Dict[str, Any]:
        stored = self._repo.all()
        return {
            "default_voice": stored.get("default_voice", VOICES[0]),
            "default_orig_vol": float(stored.get("default_orig_vol", 0.15)),
            "default_dub_vol": float(stored.get("default_dub_vol", 1.0)),
            "default_keep_source": stored.get("default_keep_source", "0") == "1",
            "whisper_model": stored.get("whisper_model", self._settings.default_whisper_model),
            "voices": list(VOICES),
            "whisper_models": list(WHISPER_MODELS),
        }

    def update(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Chỉ nhận các khóa đã biết; giá trị sai thì từ chối cả lần cập nhật."""
        values: Dict[str, str] = {}
        for key, value in changes.items():
            if value is None:
                continue
            if key == "default_voice":
                if value not in VOICES:
                    raise InvalidRequest("Giọng đọc không hợp lệ.")
                values[key] = value
            elif key == "whisper_model":
                if value not in WHISPER_MODELS:
                    raise InvalidRequest("Model Whisper không hợp lệ.")
                values[key] = value
            elif key == "default_orig_vol":
                if not 0 <= float(value) <= 1:
                    raise InvalidRequest("Âm lượng tiếng gốc phải từ 0 đến 100%.")
                values[key] = str(float(value))
            elif key == "default_dub_vol":
                if not 0.5 <= float(value) <= 2:
                    raise InvalidRequest("Âm lượng giọng Việt phải từ 50% đến 200%.")
                values[key] = str(float(value))
            elif key == "default_keep_source":
                values[key] = "1" if value else "0"
            else:
                raise InvalidRequest(f"Không có cài đặt tên '{key}'.")
        for key, value in values.items():
            self._repo.set(key, value)
        return self.get()
