---
tags: [module]
file: yt-subtitle-extension/
trạng_thái: Stable
cập_nhật: 2026-10-06
---
# Chrome Extension

"VI Subtitle Translator & TTS" v3.0.0, Manifest V3. Phát hiện phụ đề video trên trang web, dịch sang tiếng Việt, hiện phụ đề và đọc to.

## Cấu trúc
| File | Vai trò |
| --- | --- |
| `manifest.json` | Hai nhóm content script: `phim.nguonc.com` dùng `core.js` + `sites/phim.js`; mọi trang khác dùng `core.js` + `sites/generic.js` (chạy trong mọi frame) |
| `core.js` | Dùng chung: `CONFIG`, `VOL`, `SETTINGS`, `Cache` (LRU + TTL), `translate()`, `AudioDucker`, `TTSEngine`, `UI`, `PreFetcher`, `VideoSync`, lớp gốc `SubtitleAdapter` |
| `sites/generic.js` | `GenericAdapter`: 3 chiến lược theo thứ tự TextTrack API → danh sách selector quen thuộc → quét DOM gần video |
| `sites/phim.js` | `PhimAdapter`: chưa hoàn thiện, `SUBTITLE_SELECTOR` còn `null` |
| `styles.css` | Giao diện widget và overlay |

## Gọi server
`CONFIG` trong `core.js`: `API_TRANSLATE = http://127.0.0.1:8000/api/translate` (`POST` form `text`), `API_TTS = http://127.0.0.1:8000/api/tts` (`GET ?text=`), `USE_BACKEND_TTS = true`.

Có giọng với cả hai server: [[Backend Flask]] đọc bằng gTTS, [[Backend FastAPI]] đọc bằng edge-tts (từ 2026-10-06, chưa thử với extension thật).

## Thêm một trang web mới
Tạo `sites/<tên>.js` với lớp con của `SubtitleAdapter`, thêm một nhóm trong `manifest.json` và loại trang đó khỏi nhóm generic. Không sửa `core.js`.

## Cấm đụng
Logic inject DOM, giao diện, các hằng trong `CONFIG`.

## File thừa
`content.js`, `content.js.bak`, `content.js.bak2`, `app_cors_snippet.py` không được nạp: [[Phát hiện - liên hệ ẩn#Mã chết và file thừa]]. Đừng sửa nhầm `content.js`.
