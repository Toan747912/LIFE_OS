import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import os
import subprocess
from pydub import AudioSegment

def build_combined_dub_track(audio_map, output_dub_path):
    """
    Ghép tất cả các câu lồng tiếng thành 1 file Audio duy nhất với khoảng lặng (silence)
    chính xác theo timestamp. Giúp FFmpeg xử lý cực nhanh và không bị quá tải tham số command-line.
    """
    if not audio_map:
        raise ValueError("Danh sách audio_map trống!")

    # Tìm mốc thời gian kết thúc cuối cùng để tính độ dài tối thiểu của track audio
    max_end_ms = max(int(item["end"].total_seconds() * 1000) for item in audio_map) + 2000

    # Tạo track audio giữ im lặng ban đầu
    combined_track = AudioSegment.silent(duration=max_end_ms)

    for item in audio_map:
        audio_path = item["audio_path"]
        if not os.path.exists(audio_path):
            continue

        start_ms = int(item["start"].total_seconds() * 1000)
        clip = AudioSegment.from_file(audio_path)

        # Chèn câu lồng tiếng vào vị trí timestamp chính xác
        combined_track = combined_track.overlay(clip, position=start_ms)

    # Xuất file audio tổng duy nhất
    os.makedirs(os.path.dirname(output_dub_path), exist_ok=True)
    combined_track.export(output_dub_path, format="wav")
    print(f"Đã ghép hoàn tất 1 track lồng tiếng tổng hợp tại: {output_dub_path}")
    return output_dub_path

def mix_audio_to_video_advanced(video_path, audio_map, vtt_path, output_video_path, orig_vol=0.15, dub_vol=1.0, hard_sub=False, enable_dynamic_sub=False, dynamic_ass_path=None):
    """
    Trộn video với 1 track lồng tiếng duy nhất (Single-Track mixing).
    Tối ưu hiệu năng cao gấp 5 lần, giữ âm thanh gốc nhỏ làm nền và hỗ trợ phụ đề cứng/mềm/phụ đề động AI.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Không tìm thấy video tại: {video_path}")

    temp_dir = os.path.dirname(audio_map[0]["audio_path"]) if audio_map else "core/output/temp_audios"
    combined_dub_path = os.path.join(temp_dir, "combined_dubbing.wav")

    # 1. Ghép chuỗi âm thanh thành 1 file duy nhất trước khi gọi FFmpeg
    build_combined_dub_track(audio_map, combined_dub_path)

    # 2. Xây dựng lệnh FFmpeg gọn nhẹ với duy nhất 2 luồng Audio (Video gốc + Track Dub)
    input_args = [
        "-i", video_path,
        "-i", combined_dub_path
    ]

    filter_complex_str = (
        f"[0:a]volume={orig_vol}[orig]; "
        f"[1:a]volume={dub_vol}[dub]; "
        f"[orig][dub]amix=inputs=2:duration=first:normalize=0[outa]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        *input_args
    ]

    # 3. Xử lý Phụ Đề Động (Dynamic Subtitle ASS Hardsub), Phụ Đề Cứng (Hardsub) hoặc Phụ Đề Mềm (Softsub)
    if enable_dynamic_sub and dynamic_ass_path and os.path.exists(dynamic_ass_path):
        # Render phụ đề động ASS trực tiếp lên hình ảnh (Cảnh báo: Tốc độ render libx264 chậm)
        escaped_ass = dynamic_ass_path.replace('\\', '/').replace(':', '\\:')
        filter_complex_str = f"[0:v]subtitles='{escaped_ass}'[v]; " + filter_complex_str
        cmd.extend([
            "-filter_complex", filter_complex_str,
            "-map", "[v]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k"
        ])
    elif vtt_path and os.path.exists(vtt_path):
        if hard_sub:
            # Render phụ đề trực tiếp lên hình ảnh
            escaped_vtt = vtt_path.replace('\\', '/').replace(':', '\\:')
            filter_complex_str = f"[0:v]subtitles='{escaped_vtt}'[v]; " + filter_complex_str
            cmd.extend([
                "-filter_complex", filter_complex_str,
                "-map", "[v]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k"
            ])
        else:
            # Nhúng track phụ đề mềm vào MP4/MKV container
            cmd.extend(["-i", vtt_path])
            cmd.extend([
                "-filter_complex", filter_complex_str,
                "-map", "0:v:0",
                "-map", "[outa]",
                "-map", "2:s:0",
                "-c:v", "copy",     # Sao chép luồng video không tốn CPU render
                "-c:a", "aac",
                "-b:a", "192k",
                "-c:s", "mov_text" if output_video_path.endswith('.mp4') else "copy",
                "-metadata:s:s:0", "language=vie",
                "-metadata:s:s:0", "title=Tiếng Việt"
            ])
    else:
        cmd.extend([
            "-filter_complex", filter_complex_str,
            "-map", "0:v:0",
            "-map", "[outa]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k"
        ])

    cmd.append(output_video_path)

    print("Đang xuất video với FFmpeg...")
    subprocess.run(cmd, check=True)
    print(f"Hoàn tất! Video lồng tiếng thành công tại: {output_video_path}")

def mix_audio_to_video(video_path, audio_map, output_video_path):
    """Hàm tương thích ngược"""
    mix_audio_to_video_advanced(video_path, audio_map, None, output_video_path, orig_vol=0.15, dub_vol=1.0, hard_sub=False)

