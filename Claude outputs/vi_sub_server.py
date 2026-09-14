"""
VI-Sub Translation Server
Chạy server này để VI-Sub extension có thể dịch phụ đề sang tiếng Việt.
Dùng Google Translate miễn phí (không cần API key).

Cài đặt:
    pip install flask requests flask-cors

Chạy:
    python vi_sub_server.py

Server sẽ lắng nghe tại http://127.0.0.1:8000
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)  # Cho phép extension gọi từ bất kỳ origin

def translate_google(text, src='en', tgt='vi'):
    """Dịch văn bản dùng Google Translate API miễn phí."""
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        'client': 'gtx',
        'sl': src,
        'tl': tgt,
        'dt': 't',
        'q': text
    }
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    # Ghép tất cả các đoạn dịch lại
    translated = ''.join([item[0] for item in data[0] if item[0]])
    return translated

@app.route('/api/translate', methods=['POST', 'OPTIONS'])
def translate():
    if request.method == 'OPTIONS':
        return '', 204

    text = request.form.get('text', '').strip()
    if not text:
        return jsonify({'translation': ''})

    try:
        vi = translate_google(text)
        print(f"[Dịch] '{text[:50]}...' → '{vi[:50]}...'")
        return jsonify({'translation': vi})
    except Exception as e:
        print(f"[Lỗi] {e}")
        return jsonify({'translation': '', 'error': str(e)}), 500

@app.route('/api/tts', methods=['POST', 'OPTIONS'])
def tts():
    # TTS backend (optional - VI-Sub dùng Web Speech API nếu không có)
    return jsonify({'error': 'TTS backend not implemented, using Web Speech API'}), 501

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'VI-Sub server đang chạy!'})

if __name__ == '__main__':
    print("=" * 50)
    print("VI-Sub Translation Server")
    print("Server: http://127.0.0.1:8000")
    print("Nhấn Ctrl+C để dừng")
    print("=" * 50)
    app.run(host='127.0.0.1', port=8000, debug=False)
