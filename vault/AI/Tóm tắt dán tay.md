---
tags: [ai]
cập_nhật: 2026-10-05
---
# Tóm tắt dán tay

Dán nguyên khối dưới đây vào đầu phiên với ChatGPT hoặc AI không tự đọc được file. Khối này tự đủ, không cần liên kết. Khi [[Bắt đầu ở đây]] hoặc [[Trạng thái]] đổi thì cập nhật lại khối này.

```text
Bạn đang giúp tôi làm dự án LIFE_OS. Hãy tuân thủ tuyệt đối các điều sau.

DỰ ÁN
- Ứng dụng cá nhân, Windows, Python 3.11, chạy cục bộ cổng 8000, chạy từ thư mục gốc dự án.
- app.py: server FastAPI chính. vi_sub_server.py: server Flask cũ cho Chrome extension (cùng cổng 8000).
- modules/video_dubbing/ (service, sub_handler, tts_generator, media_mixer), modules/dynamic_subtitle.py,
  modules/file_manager.py, yt-subtitle-extension/, templates/index.html: STABLE, CẤM SỬA.
- modules/bilibili_dubbing/: module mới nhất, là mẫu chuẩn (OOP, tách tầng domain/storage/pipeline/api,
  dữ liệu ở data/bilibili_dubbing/, test bằng unittest).

LUẬT CỨNG
1. Chỉ sửa file tôi nêu tên trong phiên này. Không refactor, không dọn dẹp file khác.
2. Không sửa module Stable. Chỉ được gọi lại nguyên trạng.
3. Không đổi tên endpoint, không đổi hình dạng JSON trả về.
   Endpoint cũ: /start-dubbing, /status, /download-video, /api/files..., /api/translate, /api/tts, /api/bilibili/...
4. Không thêm, bớt, đổi phiên bản thư viện khi tôi chưa đồng ý.
5. Thấy lỗi ngoài phạm vi thì báo cho tôi, không tự sửa.
6. Không nói "xong" khi chưa kiểm chứng. Nói rõ cái gì đã thử, cái gì chưa.
7. Code mới: định danh tiếng Anh, docstring và thông báo tiếng Việt, pathlib.Path, không dùng đường dẫn
   tương đối theo thư mục chạy, không nuốt lỗi im lặng, không dùng biến toàn cục giữ trạng thái.
8. Tính năng mới là một module riêng trong modules/<tên>/, gắn vào app.py bằng include_router,
   không đụng module khác.

CÁCH TRẢ LỜI
- Trước khi viết code: nêu phạm vi (sẽ tạo, sửa file nào) và hỏi lại nếu yêu cầu chưa rõ.
- Đưa file hoàn chỉnh hoặc diff rõ ràng, kèm lệnh test.
- Cuối cùng: liệt kê file đã đổi, cái đã kiểm chứng, cái chưa, và những gì tôi cần ghi vào vault
  (Trạng thái, Change log, Việc cần làm, Nhật ký).
- Trên máy tôi pip.exe bị chặn: dùng "python -m pip" và "python -m uvicorn".
```
