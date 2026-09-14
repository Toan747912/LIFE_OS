"""
VI-Sub server v3 — Flask backend cho Chrome extension
  /api/translate  POST  → dịch EN sang VI qua Google Translate free API
  /api/tts        GET   → text-to-speech tiếng Việt qua gTTS (không cần Windows voice)
  /health         GET   → kiểm tra server còn sống

Cài phụ thuộc:
  pip install flask flask-cors requests gTTS
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests, time, io

app = Flask(__name__)
CORS(app)

# ─── TRANSLATION ───────────────────────────────────────────────
_trans_cache: dict[str, str] = {}

def translate_google(text: str, tgt: str = 'vi') -> str:
    if text in _trans_cache:
        return _trans_cache[text]
    url = "https://translate.googleapis.com/translate_a/single"
    params = {'client': 'gtx', 'sl': 'auto', 'tl': tgt, 'dt': 't', 'q': text}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for attempt, delay in enumerate([1, 3, 6]):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 429:
                print(f"[429] Rate limit, doi {delay}s...")
                time.sleep(delay)
                continue
            if r.status_code != 200:
                print(f"[HTTP {r.status_code}] lan {attempt+1}")
                time.sleep(delay)
                continue
            data = r.json()
            result = ''.join(
                item[0] for item in data[0]
                if isinstance(item, list) and item and item[0]
            )
            result = result.strip()
            if result:
                if len(_trans_cache) < 2000:
                    _trans_cache[text] = result
            return result
        except Exception as e:
            print(f"[ERR] {type(e).__name__}: {e}")
            time.sleep(delay)
    return ''   # KHÔNG raise → không bao giờ 500

@app.route('/api/translate', methods=['POST', 'OPTIONS'])
def translate():
    if request.method == 'OPTIONS':
        return '', 204
    text = request.form.get('text', '').strip()
    if not text:
        return jsonify({'translation': ''})
    vi = translate_google(text)
    if vi:
        print(f"[OK] {text[:50]!r} => {vi[:50]!r}")
    else:
        print(f"[SKIP] {text[:50]!r}")
    return jsonify({'translation': vi})   # luôn 200

# ─── TTS ───────────────────────────────────────────────────────
_tts_cache: dict[str, bytes] = {}

@app.route('/api/tts', methods=['GET', 'POST', 'OPTIONS'])
def tts():
    if request.method == 'OPTIONS':
        return '', 204
    text = (request.args.get('text') or request.form.get('text', '')).strip()
    if not text:
        return jsonify({'error': 'no text'}), 400

    # Trả cache nếu đã có
    if text in _tts_cache:
        return send_file(io.BytesIO(_tts_cache[text]), mimetype='audio/mpeg')

    try:
        from gtts import gTTS
        mp3_buf = io.BytesIO()
        gTTS(text=text, lang='vi', slow=False).write_to_fp(mp3_buf)
        audio_bytes = mp3_buf.getvalue()
        # Cache tối đa 300 câu
        if len(_tts_cache) < 300:
            _tts_cache[text] = audio_bytes
        print(f"[TTS] {text[:60]!r}")
        return send_file(io.BytesIO(audio_bytes), mimetype='audio/mpeg')
    except ImportError:
        msg = "gTTS chua duoc cai. Chay: pip install gTTS"
        print(f"[TTS ERR] {msg}")
        return jsonify({'error': msg}), 500
    except Exception as e:
        print(f"[TTS ERR] {e}")
        return jsonify({'error': str(e)}), 500

# ─── HEALTH ────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    try:
        from gtts import gTTS
        gtts_ok = True
    except ImportError:
        gtts_ok = False
    return jsonify({'status': 'ok', 'gtts': gtts_ok,
                    'trans_cached': len(_trans_cache),
                    'tts_cached': len(_tts_cache)})

if __name__ == '__main__':
    print("=" * 50)
    print("VI-Sub server v3 khoi dong tai http://127.0.0.1:8000")
    print("TTS: gTTS (Google Text-to-Speech, khong can Windows voice)")
    try:
        from gtts import gTTS
        print("[OK] gTTS da san sang")
    except ImportError:
        print("[!!] gTTS CHUA DUOC CAI — chay lenh sau truoc khi bat server:")
        print("     pip install gTTS")
    print("=" * 50)
    app.run(host='127.0.0.1', port=8000, debug=False)
