import os
from core.config import INPUT_DIR, OUTPUT_DIR, DEFAULT_VOICE
from modules.video_dubbing.sub_handler import load_subtitles
from modules.video_dubbing.tts_generator import generate_tts_for_subtitles
from modules.video_dubbing.media_mixer import mix_audio_to_video

def main():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    temp_audio_dir = os.path.join(OUTPUT_DIR, "temp_audios")

    print("--- Khởi động ứng dụng lồng tiếng tối ưu cho máy yếu ---")
    
    # Định nghĩa tên file đầu vào/đầu ra giả định
    sample_srt = os.path.join(INPUT_DIR, "sample.vtt")
    sample_video = os.path.join(INPUT_DIR, "sample.mp4")
    output_video = os.path.join(OUTPUT_DIR, "output_final.mp4")
    
    if os.path.exists(sample_srt) and os.path.exists(sample_video):
        # Bước 1: Đọc phụ đề
        subs = load_subtitles(sample_srt)
        print(f"Đã tải thành công {len(subs)} câu thoại.")
        
        # Bước 2: Tạo file audio tuần tự từng câu
        audio_map = generate_tts_for_subtitles(subs, DEFAULT_VOICE, temp_audio_dir)
        print(f"Hoàn tất tạo {len(audio_map)} file âm thanh tạm.")
        
        # Bước 3: Ghép vào video
        mix_audio_to_video(sample_video, audio_map, output_video)
        print("Xử lý toàn bộ quy trình thành công!")
    else:
        print(f"Lưu ý: Hãy đặt file 'sample.srt' và 'sample.mp4' vào thư mục '{INPUT_DIR}' để chạy thử.")

if __name__ == "__main__":
    main()
