/**
 * VI Subtitle Extension — sites/generic.js
 *
 * GenericAdapter: hoạt động trên mọi trang web có video + phụ đề
 * (YouTube, Coursera, v.v.)
 *
 * Yêu cầu: core.js phải được load trước.
 *
 * 3 chiến lược detect (theo thứ tự ưu tiên):
 *   1. TextTrack API  — chuẩn nhất, dùng cho YouTube / Coursera
 *   2. Known selectors — fallback với danh sách CSS selector phổ biến
 *   3. Proximity scan  — quét DOM tự động, dùng khi không biết selector
 */

// ── Danh sách selector phụ đề phổ biến ──────────────────────────
const KNOWN_SELECTORS = [
  ".ytp-caption-segment",
  ".rc-SubtitleItem", ".subtitle-item span", "[data-testid='subtitle-item']",
  ".well--text--2WPkk", "[class*='captions--captions']",
  ".subtitles li.current", ".closed-captions span",
  ".vjs-text-track-display span", ".vjs-text-track-cue span",
  "[class*='subtitle']", "[class*='caption']",
];

// ── GenericAdapter ───────────────────────────────────────────────
class GenericAdapter extends SubtitleAdapter {

  constructor() {
    super();
    this._proxInterval = null;
  }

  // ── Override: thử 3 chiến lược, trả về true nếu tìm được ──
  async detect() {
    const videos = Array.from(document.querySelectorAll("video"))
      .filter(v => v.readyState >= 1);

    if (!videos.length) return false;

    // Strategy 1: TextTrack
    for (const v of videos) {
      if (await this._tryTrackStrategy(v)) return true;
    }

    // Strategy 2: Known CSS selectors
    for (const v of videos) {
      if (this._tryKnownSelectors(v)) return true;
    }

    // Strategy 3: Proximity scan (async, self-manages)
    this._startProximityScan(videos[0]);
    return true; // scan đã bắt đầu
  }

  // ── Strategy 1: TextTrack API ────────────────────────────────
  async _tryTrackStrategy(video) {
    const tracks = Array.from(video.textTracks || []);
    const track  = tracks.find(t =>
        (t.kind === "subtitles" || t.kind === "captions") &&
        (t.language === "en" || t.language?.startsWith("en"))
      ) || tracks.find(t => t.kind === "subtitles" || t.kind === "captions");

    if (!track) return false;

    const cues = await this._waitForCues(track);
    if (!cues.length) return false;

    console.log(`[VI-Sub] Strategy 1 (track): ${cues.length} cues`);
    UI.createOverlay(video);
    VideoSync.attach(video, cues);
    PreFetcher.run(cues);
    return true;
  }

  _waitForCues(track) {
    return new Promise(resolve => {
      track.mode = "hidden";
      if (track.cues && track.cues.length > 0) return resolve(Array.from(track.cues));
      track.addEventListener("load", () => resolve(Array.from(track.cues || [])), { once: true });
      setTimeout(() => resolve(Array.from(track.cues || [])), 5000);
    });
  }

  // ── Strategy 2: Known CSS selectors ─────────────────────────
  _tryKnownSelectors(video) {
    for (const sel of KNOWN_SELECTORS) {
      try {
        const el = document.querySelector(sel);
        if (!el || !el.innerText?.trim()) continue;

        console.log("[VI-Sub] Strategy 2 (selector):", sel);
        UI.createOverlay(video);
        UI.setLabel("🔊 VI • BẬT");

        let lastText = "", debounce = null;
        new MutationObserver(() => {
          clearTimeout(debounce);
          debounce = setTimeout(async () => {
            const text = el.innerText?.trim();
            if (!text || text === lastText) return;
            lastText = text;
            const vid = document.querySelector('video');
            if (vid && vid.paused) return;
            try {
              const vi = await translate(text);
              if (vi) { UI.showSub(vi, text); TTSEngine.speak(vi); }
            } catch (_) {}
          }, CONFIG.DEBOUNCE_MS);
        }).observe(el, { childList: true, subtree: true, characterData: true });

        return true;
      } catch (_) {}
    }
    return false;
  }

  // ── Strategy 3: Proximity scan ──────────────────────────────
  _startProximityScan(video) {
    console.log("[VI-Sub] Strategy 3 (proximity scan)...");
    UI.setLabel("⏳ Đang quét...");

    const changeLog = new Map();

    this._proxInterval = setInterval(() => {
      const vr = video.getBoundingClientRect();
      if (vr.width < 100 || vr.height < 50) return;

      const area = {
        top: vr.top - 50, bottom: vr.bottom + 200,
        left: vr.left - 100, right: vr.right + 100,
      };

      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
      let node;
      while ((node = walker.nextNode())) {
        if (["SCRIPT","STYLE","NOSCRIPT"].includes(node.tagName)) continue;
        if (node.id === "vi-sub-overlay" || node.id === "vi-sub-widget") continue;

        const text = node.innerText?.trim();
        if (!text || text.length < 5 || text.length > 200) continue;
        if (text.split(" ").length < 2) continue;

        const r = node.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        if (r.top < area.top || r.bottom > area.bottom) continue;
        if (r.left < area.left || r.right > area.right) continue;

        const log = changeLog.get(node) || { count: 0, lastText: "", ts: 0 };
        if (text !== log.lastText) { log.count++; log.lastText = text; log.ts = Date.now(); }
        changeLog.set(node, log);

        if (log.count >= 2 && Date.now() - log.ts < 10_000) {
          clearInterval(this._proxInterval); this._proxInterval = null;
          console.log("[VI-Sub] Proximity locked:", node);
          UI.createOverlay(video);
          UI.setLabel("🔊 VI • BẬT");

          let lastText2 = "", debounce = null;
          new MutationObserver(() => {
            clearTimeout(debounce);
            debounce = setTimeout(async () => {
              const t = node.innerText?.trim();
              if (!t || t === lastText2) return;
              lastText2 = t;
              const vid = document.querySelector('video');
              if (vid && vid.paused) return;
              try {
                const vi = await translate(t);
                if (vi) { UI.showSub(vi, t); TTSEngine.speak(vi); }
              } catch (_) {}
            }, CONFIG.DEBOUNCE_MS);
          }).observe(node, { childList: true, subtree: true, characterData: true });
          return;
        }
      }

      const now = Date.now();
      changeLog.forEach((v, k) => { if (now - v.ts > 15_000) changeLog.delete(k); });
    }, 1500);

    setTimeout(() => {
      if (this._proxInterval) {
        clearInterval(this._proxInterval); this._proxInterval = null;
        UI.setLabel("🔊 Không thấy phụ đề");
        setTimeout(() => UI.setLabel("🔊 VI"), 3000);
      }
    }, 30_000);
  }

  // ── Override stop để dọn proxInterval ───────────────────────
  _stopAll() {
    if (this._proxInterval) { clearInterval(this._proxInterval); this._proxInterval = null; }
    super._stopAll();
  }

  // ── iframe logic (chuyển subtitle text lên top frame) ───────
  initIframe() {
    const post = msg => {
      try { window.top.postMessage({ type: "VI_IFRAME_STATUS", msg }, "*"); } catch (_) {}
    };

    const scanIframe = () => {
      const videos = document.querySelectorAll("video");
      post(`DOM scan — videos: ${videos.length}`);

      for (const video of videos) {
        const tracks = Array.from(video.textTracks || []);
        const track  = tracks.find(t =>
            (t.kind === "subtitles" || t.kind === "captions") &&
            (t.language === "en" || t.language?.startsWith("en"))
          ) || tracks.find(t => t.kind === "subtitles" || t.kind === "captions");

        if (!track) continue;
        track.mode = "hidden";

        const setup = () => {
          post(`track locked — ${track.cues?.length ?? 0} cues`);
          track.oncuechange = () => {
            const cue  = track.activeCues?.[0];
            const text = cue?.text?.replace(/<[^>]+>/g, "").trim();
            if (text) {
              try { window.top.postMessage({ type: "VI_SUB_TEXT", text }, "*"); } catch (_) {}
            }
          };
        };

        if (track.cues && track.cues.length > 0) setup();
        else track.addEventListener("load", setup, { once: true });
        return true;
      }

      // Fallback: known selectors trong iframe
      for (const sel of KNOWN_SELECTORS) {
        try {
          const el = document.querySelector(sel);
          if (!el?.innerText?.trim()) continue;
          new MutationObserver(() => {
            const text = el.innerText?.trim();
            if (text) {
              try { window.top.postMessage({ type: "VI_SUB_TEXT", text }, "*"); } catch (_) {}
            }
          }).observe(el, { childList: true, subtree: true, characterData: true });
          post(`selector locked: ${sel}`);
          return true;
        } catch (_) {}
      }

      return false;
    };

    const startWithRetry = () => {
      if (scanIframe() !== false) return;
      let attempts = 0;
      const timer = setInterval(() => {
        attempts++;
        if (scanIframe() !== false || attempts >= 20) {
          clearInterval(timer);
        }
      }, 1500);
      new MutationObserver(() => scanIframe())
        .observe(document.documentElement, { childList: true, subtree: true });
    };

    if (document.body) startWithRetry();
    else document.addEventListener("DOMContentLoaded", startWithRetry);
  }
}

// ── Auto-init ────────────────────────────────────────────────────
const _genericAdapter = new GenericAdapter();
_genericAdapter.init();

console.log("[VI-Sub] sites/generic.js loaded");
