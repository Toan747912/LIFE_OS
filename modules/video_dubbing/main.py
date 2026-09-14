import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from core.config import DEFAULT_VOICE
from modules.video_dubbing.service import DubbingConfig, run_dubbing_pipeline

def main():
    print("\n========================================")
    print("   ỨNG DỤNG LỒNG TIẾNG VIDEO (LIVE OS)")
    print("========================================")
    
    video_path = "core/input/sample.mp4"
    vtt_path = "core/input/sample.vtt"
    output_video_path = "core/output/output_final.mp4"

    if not os.path.exists(video_path) or not os.path.exists(vtt_path):
        print(f"[Lỗi]: Không tìm thấy file '{video_path}' hoặc '{vtt_path}' trong core/input/ !")
        return

    try:
        orig_input = input("Nhập âm lượng video gốc làm nền (Khuyên dùng 0.15, nhấn Enter để chọn 0.15): ").strip()
        orig_vol = float(orig_input) if orig_input else 0.15
    except ValueError:
        orig_vol = 0.15

    try:
        dub_input = input("Nhập âm lượng tiếng Việt lồng tiếng (Khuyên dùng 1.0, nhấn Enter để chọn 1.0): ").strip()
        dub_vol = float(dub_input) if dub_input else 1.0
    except ValueError:
        dub_vol = 1.0

    config = DubbingConfig(
        video_path=video_path,
        subtitle_path=vtt_path,
        output_video_path=output_video_path,
        voice=DEFAULT_VOICE,
        orig_vol=orig_vol,
        dub_vol=dub_vol,
        hard_sub=False
    )

    try:
        result = run_dubbing_pipeline(config)
        print(f"\nXử lý thành công! Video lưu tại: {result['output_path']}")
    except Exception as e:
        print(f"\n[Lỗi xử lý]: {e}")

if __name__ == "__main__":
    main()