"""
VI-Sub server v3 — Flask backend cho Chrome extension
  /api/translate  POST  → dịch EN sang VI qua Argos Translate (offline, không rate-limit)
  /api/tts        GET   → text-to-speech tiếng Việt qua gTTS (không cần Windows voice)
  /health         GET   → kiểm tra server còn sống

Cài phụ thuộc:
  pip install flask flask-cors gTTS argostranslate
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import io, time

app = Flask(__name__)
CORS(app)

# ─── ARGOS TRANSLATE SETUP ─────────────────────────────────────
_argos_ready = False
_argos_translate_fn = None

def _init_argos():
    global _argos_ready, _argos_translate_fn
    try:
        import argostranslate.package
        import argostranslate.translate

        # Kiểm tra model en→vi đã cài chưa
        installed = argostranslate.translate.get_installed_languages()
        en_lang = next((l for l in installed if l.code == 'en'), None)
        vi_lang = next((l for l in installed if l.code == 'vi'), None)

        if en_lang and vi_lang:
            trans = en_lang.get_translation(vi_lang)
            if trans:
                _argos_translate_fn = trans.translate
                _argos_ready = True
                print("[OK] Argos Translate (en→vi) san sang — dich OFFLINE")
                return

        # Chua co model → tu dong download
        print("[Argos] Chua co model en→vi, dang tai xuong...")
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        pkg = next(
            (p for p in available if p.from_code == 'en' and p.to_code == 'vi'),
            None
        )
        if pkg is None:
            print("[Argos] Khong tim thay package en→vi tren index!")
            return
        print(f"[Argos] Dang tai model: {pkg}")
        path = pkg.download()
        argostranslate.package.install_from_path(path)

        # Lay lai sau khi cai
        installed = argostranslate.translate.get_installed_languages()
        en_lang = next((l for l in installed if l.code == 'en'), None)
        vi_lang = next((l for l in installed if l.code == 'vi'), None)
        if en_lang and vi_lang:
            trans = en_lang.get_translation(vi_lang)
            if trans:
                _argos_translate_fn = trans.translate
                _argos_ready = True
                print("[OK] Argos Translate (en→vi) da cai xong — dich OFFLINE")
    except ImportError:
        print("[!!] argostranslate chua duoc cai. Chay: pip install argostranslate")
    except Exception as e:
        print(f"[Argos ERR] {e}")


# ─── TRANSLATION ───────────────────────────────────────────────
_trans_cache: dict[str, str] = {}

def translate_text(text: str) -> str:
    if text in _trans_cache:
        return _trans_cache[text]

    result = ''

    if _argos_ready and _argos_translate_fn:
        # Offline, cuc nhanh, khong rate-limit
        try:
            result = (_argos_translate_fn(text) or '').strip()
        except Exception as e:
            print(f"[Argos ERR] {e}")
    else:
        # Fallback: Google Translate free (neu Argos chua san sang)
        import requests as req
        url = "https://translate.googleapis.com/translate_a/single"
        params = {'client': 'gtx', 'sl': 'auto', 'tl': 'vi', 'dt': 't', 'q': text}
        headers = {'User-Agent': 'Mozilla/5.0'}
        for delay in [1, 3, 6]:
            try:
                r = req.get(url, params=params, headers=headers, timeout=15)
                if r.status_code == 429:
                    print(f"[429] Rate limit, doi {delay}s...")
                    time.sleep(delay)
                    continue
                if r.status_code != 200:
                    time.sleep(delay)
                    continue
                data = r.json()
                result = ''.join(
                    item[0] for item in data[0]
                    if isinstance(item, list) and item and item[0]
                ).strip()
                break
            except Exception as e:
                print(f"[ERR] {e}")
                time.sleep(delay)

    if result and len(_trans_cache) < 2000:
        _trans_cache[text] = result
    return result


@app.route('/api/translate', methods=['POST', 'OPTIONS'])
def translate():
    if request.method == 'OPTIONS':
        return '', 204
    text = request.form.get('text', '').strip()
    if not text:
        return jsonify({'translation': ''})
    vi = translate_text(text)
    if vi:
        print(f"[OK] {text[:50]!r} => {vi[:50]!r}")
    else:
        print(f"[SKIP] {text[:50]!r}")
    return jsonify({'translation': vi})


# ─── TTS ───────────────────────────────────────────────────────
_tts_cache: dict[str, bytes] = {}

@app.route('/api/tts', methods=['GET', 'POST', 'OPTIONS'])
def tts():
    if request.method == 'OPTIONS':
        return '', 204
    text = (request.args.get('text') or request.form.get('text', '')).strip()
    if not text:
        return jsonify({'error': 'no text'}), 400

    if text in _tts_cache:
        return send_file(io.BytesIO(_tts_cache[text]), mimetype='audio/mpeg')

    try:
        from gtts import gTTS
        mp3_buf = io.BytesIO()
        gTTS(text=text, lang='vi', slow=False).write_to_fp(mp3_buf)
        audio_bytes = mp3_buf.getvalue()
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
    return jsonify({
        'status': 'ok',
        'gtts': gtts_ok,
        'argos': _argos_ready,
        'trans_cached': len(_trans_cache),
        'tts_cached': len(_tts_cache),
    })


if __name__ == '__main__':
    print("=" * 50)
    print("VI-Sub server v3 khoi dong tai http://127.0.0.1:8000")
    print("Dang khoi tao Argos Translate (offline)...")
    _init_argos()
    if not _argos_ready:
        print("[!!] Argos chua san sang, dung Google fallback")
        print("     De cai Argos: pip install argostranslate")
    try:
        from gtts import gTTS
        print("[OK] gTTS da san sang")
    except ImportError:
        print("[!!] gTTS CHUA DUOC CAI — chay: pip install gTTS")
    print("=" * 50)
    app.run(host='127.0.0.1', port=8000, debug=False)
