/**
 * VI Subtitle Extension — core.js
 *
 * Shared modules dùng chung cho mọi site adapter:
 *   CONFIG, VOL, SETTINGS
 *   Cache        — LRU cache + TTL
 *   translate()  — gọi API dịch
 *   AudioDucker  — hạ volume video khi TTS đọc
 *   TTSEngine    — backend TTS + Web Speech fallback
 *   UI           — floating widget + overlay + settings panel
 *   PreFetcher   — dịch nền toàn bộ cue track
 *   VideoSync    — schedule TTS theo timeline video
 *   SubtitleAdapter — base class, subclass override detect()
 */

// ══════════════════════════════════════════════════════════════════
// CONFIG
// ══════════════════════════════════════════════════════════════════
const CONFIG = {
  API_TRANSLATE:     "http://127.0.0.1:8000/api/translate",
  API_TTS:           "http://127.0.0.1:8000/api/tts",
  USE_BACKEND_TTS:   true,

  CACHE_MAX:         500,
  CACHE_TTL_MS:      3_600_000,

  PREFETCH_BATCH:    5,
  PREFETCH_DELAY_MS: 250,

  LOOKAHEAD_SEC:     1.5,
  TTS_EARLY_MS:      180,
  DEBOUNCE_MS:       300,

  DUCK_VOLUME:       0.30,
  DUCK_FADE_IN_S:    0.20,
  DUCK_FADE_OUT_S:   0.50,

  TTS_CHARS_PER_SEC: 3.5,
  TTS_RATE_MIN:      0.75,
  TTS_RATE_MAX:      1.90,
};

// Âm lượng live (thay đổi được qua panel)
const VOL = { tts: 1.0, vid: 1.0 };

// Toggles hiển thị phụ đề
const SETTINGS = {
  showSubtitleVI:   true,
  showSubtitleOrig: true,
};


// ══════════════════════════════════════════════════════════════════
// CACHE — LRU với TTL
// ══════════════════════════════════════════════════════════════════
const Cache = (() => {
  const _map = new Map();

  function get(key) {
    const entry = _map.get(key);
    if (!entry) return null;
    if (Date.now() - entry.ts > CONFIG.CACHE_TTL_MS) { _map.delete(key); return null; }
    _map.delete(key); _map.set(key, entry);
    return entry.value;
  }

  function set(key, value) {
    if (_map.has(key)) _map.delete(key);
    _map.set(key, { value, ts: Date.now() });
    if (_map.size > CONFIG.CACHE_MAX)
      _map.delete(_map.keys().next().value);
  }

  return { get, set, has: k => get(k) !== null };
})();


// ══════════════════════════════════════════════════════════════════
// TRANSLATION API
// ══════════════════════════════════════════════════════════════════
async function translate(text) {
  const clean = text.trim();
  if (!clean) return "";

  const cached = Cache.get(clean);
  if (cached !== null) return cached;

  const fd = new FormData();
  fd.append("text", clean);
  const res = await fetch(CONFIG.API_TRANSLATE, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const { translation } = await res.json();
  const vi = translation || "";
  Cache.set(clean, vi);
  return vi;
}


// ══════════════════════════════════════════════════════════════════
// AUDIO DUCKER
// ══════════════════════════════════════════════════════════════════
const AudioDucker = (() => {
  let ctx = null, gainNode = null, bound = null;

  function setup(videoEl) {
    if (bound === videoEl) return true;
    try {
      ctx      = new (window.AudioContext || window.webkitAudioContext)();
      gainNode = ctx.createGain();
      gainNode.gain.value = 1.0;
      ctx.createMediaElementSource(videoEl).connect(gainNode);
      gainNode.connect(ctx.destination);
      bound = videoEl;
      return true;
    } catch (e) {
      console.warn("[VI-Sub] AudioDucker:", e.message);
      return false;
    }
  }

  function duck()   { if (gainNode) gainNode.gain.setTargetAtTime(CONFIG.DUCK_VOLUME, ctx.currentTime, CONFIG.DUCK_FADE_IN_S / 3); }
  function unduck() { if (gainNode) gainNode.gain.setTargetAtTime(1.0, ctx.currentTime, CONFIG.DUCK_FADE_OUT_S / 3); }
  function reset()  { if (gainNode) gainNode.gain.value = 1.0; }

  return { setup, duck, unduck, reset };
})();


// ══════════════════════════════════════════════════════════════════
// TTS ENGINE
// ══════════════════════════════════════════════════════════════════
const TTSEngine = (() => {
  let viVoice = null;
  const _audioCache = new Map();
  let _currentAudio = null;

  function loadVoice() {
    const vs = window.speechSynthesis.getVoices();
    viVoice = vs.find(v => v.lang === "vi-VN" && v.name.includes("HoaiMy"))
           || vs.find(v => v.lang === "vi-VN" && v.name.includes("NamMinh"))
           || vs.find(v => v.lang === "vi-VN")
           || vs.find(v => v.lang.startsWith("vi"))
           || null;
  }
  window.speechSynthesis.onvoiceschanged = loadVoice;
  loadVoice();

  function warmup() {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0; u.lang = "vi-VN";
      if (viVoice) u.voice = viVoice;
      window.speechSynthesis.speak(u);
    } catch (_) {}
  }

  function prefetch(text) {
    if (!CONFIG.USE_BACKEND_TTS || !text || _audioCache.has(text)) return;
    const audio = new Audio(CONFIG.API_TTS + '?text=' + encodeURIComponent(text));
    audio.preload = 'auto';
    _audioCache.set(text, audio);
  }

  function speak(text, durationMs = 0) {
    if (!text) return;

    if (CONFIG.USE_BACKEND_TTS) {
      window.speechSynthesis.cancel();
      if (_currentAudio && !_currentAudio.paused) { _currentAudio.pause(); _currentAudio = null; }

      const _audio = _audioCache.get(text) || new Audio(CONFIG.API_TTS + '?text=' + encodeURIComponent(text));
      _audioCache.delete(text);
      _audio.volume = VOL.tts;

      const applyRate = () => {
        if (durationMs > 0 && _audio.duration > 0) {
          const rate = _audio.duration / (durationMs / 1000);
          _audio.playbackRate = Math.min(2.0, Math.max(0.7, rate));
        }
      };
      if (_audio.readyState >= 1) applyRate();
      else _audio.addEventListener('loadedmetadata', applyRate, { once: true });

      _audio.onended = () => { if (_currentAudio === _audio) _currentAudio = null; };
      _audio.onerror = () => { if (_currentAudio === _audio) _currentAudio = null; };
      _currentAudio = _audio;
      _audio.play().catch(e => console.warn('[VI-Sub TTS] play blocked:', e));
      return;
    }

    // Web Speech API fallback
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "vi-VN";
    if (viVoice) utter.voice = viVoice;
    if (durationMs > 0) {
      const rate = (text.length / CONFIG.TTS_CHARS_PER_SEC * 1000) / durationMs;
      utter.rate = Math.min(CONFIG.TTS_RATE_MAX, Math.max(CONFIG.TTS_RATE_MIN, rate));
    }
    utter.onstart = () => AudioDucker.duck();
    utter.onend   = () => AudioDucker.unduck();
    utter.onerror = () => AudioDucker.unduck();
    window.speechSynthesis.speak(utter);
  }

  function pauseAudio() {
    if (_currentAudio && !_currentAudio.paused) _currentAudio.pause();
    window.speechSynthesis.pause();
  }

  function resumeAudio() {
    if (_currentAudio && _currentAudio.paused) _currentAudio.play().catch(() => {});
    window.speechSynthesis.resume();
  }

  function stop() {
    if (_currentAudio) { _currentAudio.pause(); _currentAudio = null; }
    _audioCache.clear();
    window.speechSynthesis.cancel();
    AudioDucker.unduck();
  }

  return { warmup, speak, stop, pauseAudio, resumeAudio, prefetch };
})();


// ══════════════════════════════════════════════════════════════════
// UI — Floating widget + subtitle overlay + settings panel
// ══════════════════════════════════════════════════════════════════
const UI = (() => {
  let _btn = null, _overlay = null, _panel = null, _gearBtn = null;
  let _hlTimers = [];

  function createVolumePanel() {
    if (document.getElementById("vi-vol-panel")) {
      _panel = document.getElementById("vi-vol-panel"); return;
    }
    _panel = document.createElement("div");
    _panel.id = "vi-vol-panel";
    _panel.style.cssText = `
      position:fixed; bottom:76px; right:24px; z-index:2147483647;
      background:rgba(10,10,28,0.96); border:1.5px solid rgba(251,191,36,.55);
      border-radius:16px; padding:14px 16px;
      font-family:system-ui,sans-serif; color:#fbbf24;
      font-size:13px; width:220px;
      box-shadow:0 8px 32px rgba(0,0,0,.7),0 0 0 1px rgba(251,191,36,.08);
      display:none; user-select:none;
    `;
    _panel.innerHTML = `
      <div style="font-weight:700;margin-bottom:13px;text-align:center;
                  letter-spacing:.6px;font-size:12px;opacity:.75;text-transform:uppercase">
        ⚙ Cài đặt
      </div>
      <div style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;margin-bottom:7px;font-size:12px">
          <span style="opacity:.8">🎬 Video gốc</span>
          <span id="vi-vid-val" style="font-weight:700">100%</span>
        </div>
        <input type="range" id="vi-vol-vid" min="0" max="100" value="100"
          style="width:100%;accent-color:#fbbf24;cursor:pointer;height:4px">
      </div>
      <div style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;margin-bottom:7px;font-size:12px">
          <span style="opacity:.8">🔊 Lồng tiếng VI</span>
          <span id="vi-tts-val" style="font-weight:700">100%</span>
        </div>
        <input type="range" id="vi-vol-tts" min="0" max="100" value="100"
          style="width:100%;accent-color:#fbbf24;cursor:pointer;height:4px">
      </div>
      <div style="border-top:1px solid rgba(251,191,36,.2);margin-bottom:12px"></div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:12px;opacity:.8">🌐 Phụ đề gốc</span>
        <label style="position:relative;display:inline-block;width:36px;height:20px;cursor:pointer">
          <input type="checkbox" id="vi-show-orig" checked style="opacity:0;width:0;height:0;position:absolute">
          <span id="vi-slider-orig" style="position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#444;border-radius:20px;transition:.3s;"></span>
          <span id="vi-knob-orig"   style="position:absolute;height:14px;width:14px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s;transform:translateX(0);"></span>
        </label>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:12px;opacity:.8">🇻🇳 Phụ đề VI</span>
        <label style="position:relative;display:inline-block;width:36px;height:20px;cursor:pointer">
          <input type="checkbox" id="vi-show-vi" checked style="opacity:0;width:0;height:0;position:absolute">
          <span id="vi-slider-vi" style="position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#444;border-radius:20px;transition:.3s;"></span>
          <span id="vi-knob-vi"   style="position:absolute;height:14px;width:14px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s;transform:translateX(0);"></span>
        </label>
      </div>
    `;
    document.body.appendChild(_panel);

    function toggleUI(slider, knob, on) {
      slider.style.background  = on ? '#fbbf24' : '#444';
      knob.style.transform     = on ? 'translateX(16px)' : 'translateX(0)';
      knob.style.background    = on ? '#1a1a2e' : '#fff';
    }

    const sOrig = _panel.querySelector('#vi-slider-orig'), kOrig = _panel.querySelector('#vi-knob-orig');
    const sVI   = _panel.querySelector('#vi-slider-vi'),   kVI   = _panel.querySelector('#vi-knob-vi');
    toggleUI(sOrig, kOrig, true);
    toggleUI(sVI,   kVI,   true);

    _panel.querySelector('#vi-show-orig').addEventListener('change', e => {
      SETTINGS.showSubtitleOrig = e.target.checked;
      toggleUI(sOrig, kOrig, e.target.checked);
    });
    _panel.querySelector('#vi-show-vi').addEventListener('change', e => {
      SETTINGS.showSubtitleVI = e.target.checked;
      toggleUI(sVI, kVI, e.target.checked);
    });
    _panel.querySelector('#vi-vol-vid').addEventListener('input', e => {
      VOL.vid = e.target.value / 100;
      _panel.querySelector('#vi-vid-val').textContent = e.target.value + '%';
      const vid = document.querySelector('video');
      if (vid) vid.volume = VOL.vid;
    });
    _panel.querySelector('#vi-vol-tts').addEventListener('input', e => {
      VOL.tts = e.target.value / 100;
      _panel.querySelector('#vi-tts-val').textContent = e.target.value + '%';
    });
  }

  function createButton(onToggle) {
    if (document.getElementById("vi-sub-widget")) return;

    const widget = document.createElement("div");
    widget.id = "vi-sub-widget";
    widget.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:2147483647;
      display:flex; align-items:stretch;
      background:rgba(10,10,28,0.88); border:1.5px solid rgba(251,191,36,.65);
      border-radius:50px; overflow:hidden;
      box-shadow:0 4px 20px rgba(0,0,0,.65);
      font-family:system-ui,sans-serif; user-select:none;
    `;

    _gearBtn = document.createElement("button");
    _gearBtn.title = "Cài đặt";
    _gearBtn.style.cssText = `
      background:transparent; color:rgba(251,191,36,.6); border:none;
      border-right:1px solid rgba(251,191,36,.2);
      padding:9px 13px; font-size:14px; cursor:pointer;
      transition:background .15s,color .15s; line-height:1; flex-shrink:0;
    `;
    _gearBtn.textContent = "⚙";
    _gearBtn.addEventListener("mouseenter", () => { _gearBtn.style.background = "rgba(251,191,36,.1)"; _gearBtn.style.color = "#fbbf24"; });
    _gearBtn.addEventListener("mouseleave", () => {
      const open = _panel && _panel.style.display !== "none";
      _gearBtn.style.background = open ? "rgba(251,191,36,.15)" : "transparent";
      _gearBtn.style.color      = open ? "#fbbf24" : "rgba(251,191,36,.6)";
    });
    _gearBtn.addEventListener("click", e => {
      e.stopPropagation();
      if (!_panel) return;
      const showing = _panel.style.display !== "none";
      _panel.style.display       = showing ? "none" : "block";
      _gearBtn.style.background  = showing ? "transparent" : "rgba(251,191,36,.15)";
      _gearBtn.style.color       = showing ? "rgba(251,191,36,.6)" : "#fbbf24";
    });

    _btn = document.createElement("button");
    _btn.id    = "vi-sub-btn";
    _btn.title = "Bật/tắt phụ đề tiếng Việt";
    _btn.style.cssText = `
      background:transparent; color:#fbbf24; border:none;
      padding:9px 18px 9px 14px; font-size:13px; font-weight:700; cursor:pointer;
      transition:background .15s,color .15s; white-space:nowrap; line-height:1; letter-spacing:.4px;
    `;
    _btn.textContent = "🔊 VI";
    _btn.addEventListener("mouseenter", () => { if (!_btn._active) _btn.style.background = "rgba(251,191,36,.08)"; });
    _btn.addEventListener("mouseleave", () => { if (!_btn._active) _btn.style.background = "transparent"; });
    _btn.addEventListener("click", onToggle);

    widget.appendChild(_gearBtn);
    widget.appendChild(_btn);
    document.body.appendChild(widget);
    createVolumePanel();
  }

  function setActive(active) {
    if (!_btn) return;
    _btn._active = active;
    const widget = document.getElementById("vi-sub-widget");
    if (active) {
      _btn.style.background = "#fbbf24";
      _btn.style.color      = "#1a1a2e";
      if (widget) widget.style.boxShadow = "0 4px 20px rgba(0,0,0,.65),0 0 14px rgba(251,191,36,.3)";
    } else {
      _btn.style.background = "transparent";
      _btn.style.color      = "#fbbf24";
      if (widget) widget.style.boxShadow = "0 4px 20px rgba(0,0,0,.65)";
      if (_panel) _panel.style.display = "none";
      if (_gearBtn) { _gearBtn.style.background = "transparent"; _gearBtn.style.color = "rgba(251,191,36,.6)"; }
    }
  }

  function setLabel(text) { if (_btn) _btn.textContent = text; }

  function createOverlay(videoEl) {
    const existing = document.getElementById("vi-sub-overlay");
    if (existing) { _overlay = existing; return; }
    _overlay = document.createElement("div");
    _overlay.id = "vi-sub-overlay";
    _overlay.style.cssText = `
      display:none; position:absolute; bottom:12%; left:50%;
      transform:translateX(-50%); z-index:99999; pointer-events:none;
      width:84%; text-align:center; font-family:system-ui,sans-serif;
      transition:opacity .15s ease;
    `;
    const wrapper = videoEl.parentElement || document.body;
    if (wrapper !== document.body) wrapper.style.position ||= "relative";
    wrapper.appendChild(_overlay);
  }

  function showSub(viText, enText = '', durationMs = 0) {
    if (!_overlay) return;
    if (!SETTINGS.showSubtitleOrig && !SETTINGS.showSubtitleVI) { hideSub(); return; }

    _hlTimers.forEach(t => clearTimeout(t));
    _hlTimers = [];
    let html = '';

    if (enText && SETTINGS.showSubtitleOrig) {
      const words = enText.split(' ');
      const spans = words.map((w, i) =>
        `<span id="vi-en-w${i}" style="color:#fff;text-shadow:0 0 5px #000,0 0 5px #000;font-weight:600;transition:color .1s,text-shadow .1s;">${w}</span>`
      ).join(' ');
      html += `<div style="font-size:1.12em;line-height:1.4;margin-bottom:${SETTINGS.showSubtitleVI && viText ? '6px' : '0'};">${spans}</div>`;

      if (durationMs > 0 && words.length > 0) {
        const msPerWord = durationMs / words.length;
        words.forEach((_, i) => {
          const t = setTimeout(() => {
            if (i > 0) {
              const prev = _overlay.querySelector(`#vi-en-w${i - 1}`);
              if (prev) { prev.style.color = '#ccc'; prev.style.textShadow = '0 0 4px #000'; prev.style.fontWeight = '500'; }
            }
            const curr = _overlay.querySelector(`#vi-en-w${i}`);
            if (curr) { curr.style.color = '#fbbf24'; curr.style.textShadow = '0 0 12px #fbbf24,0 0 6px #fbbf24,0 0 4px #000'; curr.style.fontWeight = '800'; }
          }, i * msPerWord);
          _hlTimers.push(t);
        });
      }
    }

    if (viText && SETTINGS.showSubtitleVI) {
      html += `<div style="font-size:.86em;color:#fde68a;text-shadow:0 0 5px #000,0 0 5px #000;font-weight:500;opacity:.92;line-height:1.4;">${viText}</div>`;
    }

    if ((!enText || !SETTINGS.showSubtitleOrig) && viText && SETTINGS.showSubtitleVI) {
      html = `<div style="font-size:1.1em;color:#fbbf24;text-shadow:0 0 5px #000,0 0 5px #000;font-weight:600;line-height:1.4;">${viText}</div>`;
    }

    _overlay.innerHTML = html;
    _overlay.style.display = "block";
    _overlay.style.opacity = "1";
  }

  function clearHighlightTimers() { _hlTimers.forEach(t => clearTimeout(t)); _hlTimers = []; }

  function hideSub() {
    if (!_overlay) return;
    _hlTimers.forEach(t => clearTimeout(t)); _hlTimers = [];
    _overlay.style.opacity = "0";
    setTimeout(() => { if (_overlay) _overlay.style.display = "none"; }, 160);
  }

  function destroyOverlay() {
    const el = document.getElementById("vi-sub-overlay");
    if (el) el.remove();
    _overlay = null;
  }

  return { createButton, setActive, setLabel, createOverlay, showSub, hideSub, destroyOverlay, clearHighlightTimers };
})();


// ══════════════════════════════════════════════════════════════════
// PRE-FETCHER
// ══════════════════════════════════════════════════════════════════
const PreFetcher = (() => {
  let _active = false;

  async function run(cues) {
    _active = true;
    for (let i = 0; i < cues.length; i += CONFIG.PREFETCH_BATCH) {
      if (!_active) break;
      const batch = cues.slice(i, i + CONFIG.PREFETCH_BATCH);
      await Promise.allSettled(batch.map(async cue => {
        const text = cue.text.replace(/<[^>]+>/g, "").trim();
        if (!text || Cache.has(text)) return;
        try { const vi = await translate(text); if (vi) TTSEngine.prefetch(vi); } catch (_) {}
      }));
      const pct = Math.min(100, Math.round((i + batch.length) / cues.length * 100));
      UI.setLabel(`⏳ ${pct}%`);
      if (i + CONFIG.PREFETCH_BATCH < cues.length)
        await new Promise(r => setTimeout(r, CONFIG.PREFETCH_DELAY_MS));
    }
    if (_active) UI.setLabel("🔊 VI • BẬT");
  }

  function stop() { _active = false; }
  return { run, stop };
})();


// ══════════════════════════════════════════════════════════════════
// VIDEO SYNC ENGINE
// ══════════════════════════════════════════════════════════════════
const VideoSync = (() => {
  let _cues = [], _enabled = false, _timerId = null;
  let _lastTime = 0, _videoEl = null, _activeCueEnd = 0;
  const _done = new Set();
  const _pendingTimeouts = new Set();

  function _onVideoPause() {
    _pendingTimeouts.forEach(t => clearTimeout(t)); _pendingTimeouts.clear();
    TTSEngine.pauseAudio();
    UI.clearHighlightTimers();
  }

  function _onVideoPlay() { TTSEngine.resumeAudio(); }

  function _tick() {
    if (!_enabled) return;
    const vid = document.querySelector('video');
    if (!vid) return;

    const currentTime = vid.currentTime;
    if (Math.abs(currentTime - _lastTime) > 1.5) {
      _done.clear();
      _pendingTimeouts.forEach(t => clearTimeout(t)); _pendingTimeouts.clear();
      _activeCueEnd = 0;
      TTSEngine.stop(); UI.hideSub();
    }
    _lastTime = currentTime;
    if (vid.paused) return;

    if (_activeCueEnd > 0 && currentTime >= _activeCueEnd + 0.08) {
      _activeCueEnd = 0; UI.hideSub();
    }

    AudioDucker.setup(vid);
    if (Math.abs(vid.volume - VOL.vid) > 0.01) vid.volume = VOL.vid;

    const rate = vid.playbackRate || 1;
    _cues.forEach((cue, idx) => {
      if (_done.has(idx)) return;
      if (cue.startTime < currentTime - 0.3) { _done.add(idx); return; }
      if (cue.startTime - currentTime > CONFIG.LOOKAHEAD_SEC * 2) return;

      if (cue.startTime - currentTime <= CONFIG.LOOKAHEAD_SEC) {
        _done.add(idx);
        const delayMs = Math.max(0, (cue.startTime - currentTime) * 1000 / rate - CONFIG.TTS_EARLY_MS);
        const tid = setTimeout(async () => {
          _pendingTimeouts.delete(tid);
          if (!_enabled) return;
          const vNow = document.querySelector('video');
          if (!vNow || vNow.paused) return;
          if (Math.abs(vNow.currentTime - cue.startTime) > 2.0) return;

          const text = cue.text.replace(/<[^>]+>/g, "").trim();
          if (!text) return;
          try {
            const vi = await translate(text);
            const durationMs = (cue.endTime - cue.startTime) * 1000;
            if (!vi || !_enabled) return;
            const vCheck = document.querySelector('video');
            if (!vCheck || vCheck.paused) return;
            _activeCueEnd = cue.endTime;
            UI.showSub(vi, text, durationMs);
            TTSEngine.speak(vi, durationMs);
          } catch (e) { console.warn("[VI-Sub] cue error:", e.message); }
        }, delayMs);
        _pendingTimeouts.add(tid);
      }
    });
  }

  function attach(videoEl, cues) {
    detach();
    _cues = cues; _enabled = true; _done.clear(); _lastTime = 0;
    if (videoEl) {
      AudioDucker.setup(videoEl);
      videoEl.addEventListener('pause', _onVideoPause);
      videoEl.addEventListener('play',  _onVideoPlay);
      _videoEl = videoEl;
    }
    _timerId = setInterval(_tick, 250);
  }

  function detach() {
    if (_timerId) { clearInterval(_timerId); _timerId = null; }
    if (_videoEl) {
      _videoEl.removeEventListener('pause', _onVideoPause);
      _videoEl.removeEventListener('play',  _onVideoPlay);
      _videoEl = null;
    }
    _pendingTimeouts.forEach(t => clearTimeout(t)); _pendingTimeouts.clear();
    _done.clear(); _cues = []; _enabled = false; _activeCueEnd = 0;
    TTSEngine.stop();
  }

  return { attach, detach };
})();


// ══════════════════════════════════════════════════════════════════
// SUBTITLE ADAPTER — Base class
// Mỗi site tạo 1 subclass, override detect() + initIframe() nếu cần
// ══════════════════════════════════════════════════════════════════
class SubtitleAdapter {
  constructor() {
    this._isEnabled  = false;
    this._retryTimer = null;
    this._domWatcher = null;
  }

  /**
   * Tìm nguồn subtitle trên trang hiện tại.
   * Trả về true nếu đã attach được VideoSync hoặc MutationObserver.
   * @returns {Promise<boolean>}
   */
  async detect() {
    throw new Error(`[VI-Sub] ${this.constructor.name}.detect() chưa được implement`);
  }

  /** Gọi khi user bấm bật — subclass thường không cần override */
  start() {
    this._isEnabled = true;
    UI.setActive(true);
    TTSEngine.warmup();
    UI.setLabel("⏳ Đang tìm...");
    this._startAll();
  }

  /** Gọi khi user bấm tắt */
  stop() {
    this._isEnabled = false;
    UI.setActive(false);
    this._stopAll();
    UI.setLabel("🔊 VI");
  }

  async _startAll() {
    this._stopWatchers();
    const found = await this.detect();
    if (found) return;

    UI.setLabel("⏳ Chờ video...");
    let attempts = 0;
    this._retryTimer = setInterval(async () => {
      attempts++;
      if (!this._isEnabled) { this._stopWatchers(); return; }
      const found = await this.detect();
      if (found) { this._stopWatchers(); return; }
      if (attempts >= 15) {
        this._stopWatchers();
        UI.setLabel("⏳ Chờ phụ đề...");
      }
    }, 2000);

    this._domWatcher = new MutationObserver(async () => {
      if (!this._isEnabled) return;
      if (await this.detect()) this._stopWatchers();
    });
    this._domWatcher.observe(document.documentElement, { childList: true, subtree: true });
  }

  _stopAll() {
    this._stopWatchers();
    PreFetcher.stop();
    VideoSync.detach();
    TTSEngine.stop();
    AudioDucker.reset();
    UI.hideSub();
    UI.destroyOverlay();
  }

  _stopWatchers() {
    if (this._retryTimer) { clearInterval(this._retryTimer); this._retryTimer = null; }
    if (this._domWatcher) { this._domWatcher.disconnect(); this._domWatcher = null; }
  }

  /**
   * Khởi tạo floating button và message listener (top frame).
   * Subclass có thể override để thêm logic riêng.
   */
  init() {
    const IS_TOP_FRAME = window.self === window.top;
    if (IS_TOP_FRAME) {
      const doInit = () => {
        UI.createButton(() => {
          if (this._isEnabled) this.stop();
          else this.start();
        });
      };
      if (document.body) doInit();
      else document.addEventListener("DOMContentLoaded", doInit);

      window.addEventListener("message", async e => {
        if (e.data?.type === "VI_IFRAME_STATUS") {
          if (this._isEnabled && e.data.msg?.includes("track locked"))
            UI.setLabel("🔊 VI • BẬT");
          return;
        }
        if (!this._isEnabled || e.data?.type !== "VI_SUB_TEXT") return;
        const text = e.data.text?.trim();
        if (!text) return;
        try {
          const vi = await translate(text);
          if (vi) { UI.showSub(vi, text); TTSEngine.speak(vi); }
        } catch (_) {}
      });
    } else {
      this.initIframe();
    }
  }

  /**
   * Logic cho iframe — override nếu site cần xử lý iframe khác.
   * Mặc định: không làm gì (site không dùng iframe để truyền subtitle).
   */
  initIframe() {}
}

console.log("[VI-Sub] core.js loaded");
