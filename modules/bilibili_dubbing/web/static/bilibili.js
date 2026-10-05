/* Giao diện module Bilibili Dubbing — giai đoạn 1: quét link và chọn cấu hình.
   Mọi nội dung lấy từ Bilibili (tiêu đề, tên tập...) đều gán qua textContent, không dùng innerHTML. */
(function () {
  "use strict";

  const API = "/api/bilibili";
  const state = { scan: null, selection: {} }; // selection[key] = { checked, format, subtitle }

  const $ = (id) => document.getElementById(id);
  const el = (tag, props = {}, children = []) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    });
    children.forEach((c) => node.appendChild(c));
    return node;
  };

  async function api(path, options = {}) {
    const isForm = options.body instanceof FormData;   // upload file: để trình duyệt tự đặt Content-Type
    const response = await fetch(API + path, {
      headers: isForm ? {} : { "Content-Type": "application/json" },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.error || (typeof data.detail === "string" ? data.detail : null);
      throw new Error(detail || `Lỗi máy chủ (${response.status})`);
    }
    return data;
  }

  const formatDuration = (s) => {
    if (s == null) return "—";
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    const mm = String(m).padStart(h ? 2 : 1, "0"), ss = String(sec).padStart(2, "0");
    return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  };
  const formatSize = (bytes) => {
    if (!bytes) return "";
    const mb = bytes / 1048576;
    return mb >= 1024 ? ` · ~${(mb / 1024).toFixed(1)} GB` : ` · ~${Math.round(mb)} MB`;
  };
  const keyOf = (resultIndex, episodeId) => `${resultIndex}:${episodeId}`;

  // ── Tab ────────────────────────────────────────────────────────────────────
  let activeTab = "create";
  function switchTab(name) {
    activeTab = name;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
    if (name !== "review") stopReviewVideo();
    if (name === "queue") loadJobs();
    if (name === "review" && $("review-editor").classList.contains("hidden")) loadReviewList();
    if (name === "library") { closePlayer(); loadLibraryFilters().then(loadLibrary); }
    if (name === "settings") { loadDefaults(); loadStorage(); loadTaxonomy(); }
    else clearTimeout(storageTimer);
  }
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.addEventListener("click", () => switchTab(tab.dataset.tab)));

  /* Nút xóa hai bước, thay cho hộp thoại xác nhận của trình duyệt. */
  function confirmButton(label, confirmLabel, action) {
    const button = el("button", { class: "small danger", text: label });
    let armed = false, timer = null;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!armed) {
        armed = true;
        button.textContent = confirmLabel;
        timer = setTimeout(() => { armed = false; button.textContent = label; }, 4000);
        return;
      }
      clearTimeout(timer);
      button.disabled = true;
      action();
    });
    return button;
  }

  // ── Tình trạng phụ thuộc ───────────────────────────────────────────────────
  async function loadHealth() {
    const box = $("health");
    box.replaceChildren();
    try {
      const h = await api("/health");
      if (!h.yt_dlp) box.appendChild(el("div", { class: "notice error",
        text: "Chưa cài yt-dlp nên chưa quét được. Chạy: pip install -r requirements.txt rồi khởi động lại server." }));
      if (!h.ffmpeg) box.appendChild(el("div", { class: "notice error",
        text: "Không tìm thấy ffmpeg trong PATH. Cần ffmpeg để ghép video và lồng tiếng." }));
      if (!h.edge_tts) box.appendChild(el("div", { class: "notice error",
        text: "Chưa cài edge-tts nên bước sinh giọng sẽ thất bại. Chạy: python -m pip install edge-tts" }));
      if (!h.deep_translator) box.appendChild(el("div", { class: "notice error",
        text: "Chưa cài deep-translator nên không dịch được phụ đề. Chạy: python -m pip install -r requirements.txt" }));
      if (!h.cookie_configured) box.appendChild(el("div", { class: "notice",
        text: "Chưa có cookie Bilibili: chỉ thấy chất lượng công khai (thường tới 480p) và không lấy được phụ đề AI." }));
    } catch (err) {
      box.appendChild(el("div", { class: "notice error", text: "Không kết nối được API: " + err.message }));
    }
  }

  // ── Quét ───────────────────────────────────────────────────────────────────
  async function runScan() {
    const urls = $("urls").value.split(/[\s,]+/).filter(Boolean);
    if (!urls.length) { $("scan-status").textContent = "Hãy dán ít nhất một link."; return; }
    $("scan-btn").disabled = true;
    $("scan-status").textContent = `Đang quét ${urls.length} link, có thể mất vài chục giây…`;
    try {
      state.scan = await api("/scan", { method: "POST", body: JSON.stringify({ urls }) });
      state.selection = {};
      state.scan.results.forEach((result, ri) =>
        result.episodes.forEach((ep) => initSelection(ri, ep, result.episodes.length === 1)));
      $("scan-status").textContent = "";
      render();
    } catch (err) {
      $("scan-status").textContent = "Quét thất bại: " + err.message;
    } finally {
      $("scan-btn").disabled = false;
    }
  }

  function defaultFormat(ep) {
    const playable = ep.formats.filter((f) => f.browser_playable);
    const pool = playable.length ? playable : ep.formats;
    const upTo1080 = pool.filter((f) => f.height <= 1080);
    return (upTo1080[0] || pool[pool.length - 1] || {}).format_id || "";
  }

  function defaultSubtitle(ep) {
    const uploaded = ep.subtitles.find((s) => s.kind === "uploaded");
    const any = uploaded || ep.subtitles[0];
    return any ? "platform:" + any.lang : "whisper";
  }

  function initSelection(ri, ep, checked) {
    const prev = state.selection[keyOf(ri, ep.episode_id)];
    state.selection[keyOf(ri, ep.episode_id)] = {
      checked: prev ? prev.checked : (checked && ep.accessible && ep.probed),
      format: defaultFormat(ep),
      subtitle: defaultSubtitle(ep),
    };
  }

  async function probe(ri, ep, button) {
    button.disabled = true;
    button.textContent = "Đang quét…";
    try {
      const updated = await api(`/scan/${state.scan.scan_id}/probe`, {
        method: "POST", body: JSON.stringify({ result_index: ri, episode_id: ep.episode_id }),
      });
      const episodes = state.scan.results[ri].episodes;
      episodes[episodes.findIndex((e) => e.episode_id === ep.episode_id)] = updated;
      initSelection(ri, updated, false);
      render();
    } catch (err) {
      button.disabled = false;
      button.textContent = "Thử lại";
      $("scan-status").textContent = err.message;
    }
  }

  // ── Hiển thị ───────────────────────────────────────────────────────────────
  function render() {
    const box = $("results");
    box.replaceChildren();
    if (!state.scan) return;
    $("options").classList.remove("hidden");
    $("start-bar").classList.remove("hidden");
    box.appendChild(el("h2", { text: "3. Chọn tập, chất lượng và phụ đề" }));
    state.scan.results.forEach((result, ri) => box.appendChild(renderResult(result, ri)));
    updateSummary();
  }

  function renderResult(result, ri) {
    const card = el("div", { class: "card" });
    if (!result.ok) {
      card.appendChild(el("div", { class: "card-head" }, [el("div", {}, [
        el("div", { class: "card-title", text: result.url }),
      ])]));
      card.appendChild(el("div", { class: "card-error", text: result.error || "Không quét được link." }));
      return card;
    }
    const head = el("div", { class: "card-head" });
    if (result.thumbnail) head.appendChild(el("img", { src: result.thumbnail, alt: "", referrerpolicy: "no-referrer" }));
    head.appendChild(el("div", {}, [
      el("div", { class: "card-title", text: result.title || result.url }),
      el("div", { class: "muted", text:
        [result.uploader, result.kind === "playlist" ? `${result.episodes.length} tập` : "Video đơn"]
          .filter(Boolean).join(" · ") }),
    ]));
    card.appendChild(head);

    const table = el("table");
    table.appendChild(el("thead", {}, [el("tr", {}, [
      el("th", {}, [masterCheckbox(result, ri)]),
      el("th", { text: "Tập" }), el("th", { text: "Thời lượng" }),
      el("th", { text: "Chất lượng" }), el("th", { text: "Nguồn phụ đề" }),
    ])]));
    const body = el("tbody");
    result.episodes.forEach((ep) => body.appendChild(renderEpisode(ep, ri)));
    table.appendChild(body);
    card.appendChild(el("div", { class: "table-wrap" }, [table]));
    return card;
  }

  function masterCheckbox(result, ri) {
    const selectable = result.episodes.filter((ep) => ep.probed && ep.accessible);
    const box = el("input", { type: "checkbox", title: "Chọn tất cả tập đã quét" });
    box.checked = selectable.length > 0 &&
      selectable.every((ep) => state.selection[keyOf(ri, ep.episode_id)].checked);
    box.disabled = selectable.length === 0;
    box.addEventListener("change", () => {
      selectable.forEach((ep) => { state.selection[keyOf(ri, ep.episode_id)].checked = box.checked; });
      render();
    });
    return box;
  }

  function renderEpisode(ep, ri) {
    const sel = state.selection[keyOf(ri, ep.episode_id)];
    const row = el("tr");
    const check = el("input", { type: "checkbox" });
    check.checked = sel.checked;
    check.disabled = !(ep.probed && ep.accessible);
    check.addEventListener("change", () => { sel.checked = check.checked; updateSummary(); });
    row.appendChild(el("td", {}, [check]));
    row.appendChild(el("td", { class: "title", text: `${ep.index}. ${ep.title}` }));
    row.appendChild(el("td", { text: (ep.duration_estimated ? "~" : "") + formatDuration(ep.duration_s) }));

    if (!ep.probed) {
      const button = el("button", { class: "small", text: "Quét chi tiết" });
      button.addEventListener("click", () => probe(ri, ep, button));
      row.appendChild(el("td", { colspan: "2" }, [button]));
      return row;
    }
    if (!ep.accessible) {
      row.appendChild(el("td", { colspan: "2" }, [
        el("span", { class: "badge err", text: ep.error || "Không truy cập được" }),
      ]));
      return row;
    }

    const quality = el("select");
    ep.formats.forEach((f) => {
      const option = el("option", { value: f.format_id,
        text: f.label + formatSize(f.size_bytes) + (f.browser_playable ? "" : " · không phát được trên web") });
      quality.appendChild(option);
    });
    quality.value = sel.format;
    quality.addEventListener("change", () => { sel.format = quality.value; });
    row.appendChild(el("td", {}, [quality]));

    const subtitle = el("select");
    ep.subtitles.forEach((s) => subtitle.appendChild(
      el("option", { value: "platform:" + s.lang, text: `Có sẵn: ${s.name}` })));
    subtitle.appendChild(el("option", { value: "whisper", text: "Whisper tự bóc băng (thử nghiệm, cần nhiều RAM)" }));
    subtitle.appendChild(el("option", { value: "uploaded", text: "Tôi sẽ upload file phụ đề" }));
    subtitle.value = sel.subtitle;
    subtitle.addEventListener("change", () => { sel.subtitle = subtitle.value; });
    const cell = el("td", {}, [subtitle]);
    if (!ep.subtitles.length) cell.appendChild(el("div", { class: "muted", text: "Link này không có phụ đề sẵn" }));
    row.appendChild(cell);
    return row;
  }

  function updateSummary() {
    const count = Object.values(state.selection).filter((s) => s.checked).length;
    $("selection-summary").textContent = count ? `Đã chọn ${count} tập.` : "Chưa chọn tập nào.";
    $("start-btn").disabled = count === 0;
  }

  // ── Tạo job ────────────────────────────────────────────────────────────────
  async function startJobs() {
    const items = Object.entries(state.selection).filter(([, sel]) => sel.checked).map(([key, sel]) => {
      const [resultIndex, episodeId] = key.split(/:(.*)/s);
      return { result_index: Number(resultIndex), episode_id: episodeId, format_id: sel.format, subtitle: sel.subtitle };
    });
    if (!items.length) return;
    $("start-btn").disabled = true;
    try {
      await api("/jobs", { method: "POST", body: JSON.stringify({
        scan_id: state.scan.scan_id, items,
        voice: $("opt-voice").value,
        orig_vol: Number($("opt-orig").value) / 100,
        dub_vol: Number($("opt-dub").value) / 100,
        keep_source: $("opt-keep").checked,
      }) });
      Object.values(state.selection).forEach((sel) => { sel.checked = false; });
      render();
      switchTab("queue");
    } catch (err) {
      $("selection-summary").textContent = "Không tạo được job: " + err.message;
      $("start-btn").disabled = false;
    }
  }

  // ── Hàng đợi ───────────────────────────────────────────────────────────────
  const STATUS_LABELS = {
    QUEUED: "Đang chờ", DOWNLOADING: "Đang tải", PREPARING_SUBS: "Lấy phụ đề", TRANSLATING: "Đang dịch",
    AWAITING_SUBTITLE: "Chờ phụ đề",
    AWAITING_REVIEW: "Chờ bạn duyệt", SYNTHESIZING: "Sinh giọng", MIXING: "Trộn video",
    PUBLISHING: "Đưa vào thư viện", DONE: "Hoàn tất", FAILED: "Thất bại", CANCELLED: "Đã hủy",
  };
  const ENDED = ["DONE", "FAILED", "CANCELLED"];
  const WAITING = ["AWAITING_SUBTITLE", "AWAITING_REVIEW"];   // dừng chờ người dùng, không tự thay đổi
  let pollTimer = null;

  async function loadJobs() {
    clearTimeout(pollTimer);
    try {
      const { jobs } = await api("/jobs");
      renderJobs(jobs);
      const busy = jobs.some((job) => !ENDED.includes(job.status) && !WAITING.includes(job.status));
      if (busy && activeTab === "queue") pollTimer = setTimeout(loadJobs, 2000);
    } catch (err) {
      $("queue-message").textContent = "Không tải được hàng đợi: " + err.message;
      if (activeTab === "queue") pollTimer = setTimeout(loadJobs, 5000);
    }
  }

  async function jobAction(path, method) {
    try { await api(path, { method }); }
    catch (err) { $("queue-message").textContent = err.message; }
    loadJobs();
  }

  function renderJobs(jobs) {
    const box = $("queue-list");
    box.replaceChildren();
    $("queue-clear").classList.toggle("hidden", !jobs.some((job) => job.status === "DONE"));
    if (!jobs.length) {
      box.appendChild(el("p", { class: "placeholder", text: "Chưa có job nào. Sang tab Tạo mới để bắt đầu." }));
      return;
    }
    jobs.forEach((job) => {
      const ended = ENDED.includes(job.status);
      const badgeClass = job.status === "DONE" ? "badge ok" : job.status === "FAILED" ? "badge err"
        : WAITING.includes(job.status) ? "badge" : "badge info";
      const card = el("div", { class: "job" });
      card.appendChild(el("div", { class: "job-head" }, [
        el("div", {}, [
          el("div", { class: "job-title", text: job.title }),
          el("div", { class: "muted", text: [job.series_title, job.episode_label, job.quality_label].filter(Boolean).join(" · ") }),
        ]),
        el("span", { class: badgeClass, text: STATUS_LABELS[job.status] || job.status }),
      ]));
      if (WAITING.includes(job.status)) {
        card.appendChild(el("div", { class: "muted", text: job.message }));
      } else if (!ended) {
        const fill = el("span");
        fill.style.width = job.progress + "%";
        card.appendChild(el("div", { class: "bar" }, [fill]));
        card.appendChild(el("div", { class: "muted", text: `${job.progress}% · ${job.message}` }));
      }
      if (job.error) card.appendChild(el("div", { class: "job-error", text: job.error }));
      const actions = el("div", { class: "job-actions" });
      if (job.status === "DONE" && job.item_id) {
        const view = el("button", { class: "small primary", text: "Xem video" });
        view.addEventListener("click", () => { switchTab("library"); openPlayer(job.item_id); });
        actions.appendChild(view);
      }
      if (job.status === "AWAITING_REVIEW") {
        const review = el("button", { class: "small primary", text: "Duyệt phụ đề" });
        review.addEventListener("click", () => { switchTab("review"); openReview(job.id); });
        actions.appendChild(review);
      }
      if (job.status === "AWAITING_SUBTITLE") {
        const input = el("input", { type: "file", accept: ".srt,.vtt", class: "hidden" });
        input.addEventListener("change", () => { if (input.files.length) uploadSubtitle(job.id, input.files[0]); });
        const pick = el("button", { class: "small primary", text: "Upload phụ đề (.srt, .vtt)" });
        pick.addEventListener("click", () => input.click());
        const whisper = el("button", { class: "small", text: "Dùng Whisper bóc băng" });
        whisper.addEventListener("click", () => jobAction(`/jobs/${job.id}/use-whisper`, "POST"));
        actions.append(input, pick, whisper);
      }
      if (!ended) {
        const cancel = el("button", { class: "small", text: "Hủy" });
        cancel.addEventListener("click", () => jobAction(`/jobs/${job.id}/cancel`, "POST"));
        actions.appendChild(cancel);
      }
      if (job.status === "FAILED" || job.status === "CANCELLED") {
        const retry = el("button", { class: "small", text: "Chạy lại" });
        retry.addEventListener("click", () => jobAction(`/jobs/${job.id}/retry`, "POST"));
        actions.appendChild(retry);
      }
      if (ended) actions.appendChild(confirmButton("Xóa khỏi danh sách", "Bấm lần nữa để xóa",
        () => jobAction(`/jobs/${job.id}`, "DELETE")));
      card.appendChild(actions);
      box.appendChild(card);
    });
  }

  async function uploadSubtitle(jobId, file) {
    const form = new FormData();
    form.append("file", file);
    try { await api(`/jobs/${jobId}/subtitle`, { method: "POST", body: form }); }
    catch (err) { $("queue-message").textContent = "Không nhận được file phụ đề: " + err.message; }
    loadJobs();
  }

  // ── Duyệt phụ đề ───────────────────────────────────────────────────────────
  const review = { jobId: null, cues: [], dirty: new Map(), rows: new Map(), video: null };
  const formatClock = (ms) => formatDuration(Math.floor(ms / 1000));

  function stopReviewVideo() {
    if (review.video) review.video.pause();
  }

  async function loadReviewList() {
    const box = $("review-list");
    try {
      const { jobs } = await api("/jobs");
      const waiting = jobs.filter((job) => job.status === "AWAITING_REVIEW");
      box.replaceChildren();
      $("review-message").textContent = waiting.length ? "" : "Không có video nào đang chờ duyệt.";
      waiting.forEach((job) => {
        const open = el("button", { class: "small primary", text: "Mở để duyệt" });
        open.addEventListener("click", () => openReview(job.id));
        box.appendChild(el("div", { class: "job" }, [
          el("div", { class: "job-title", text: job.title }),
          el("div", { class: "muted", text: job.message }),
          el("div", { class: "job-actions" }, [open]),
        ]));
      });
    } catch (err) {
      $("review-message").textContent = "Không tải được danh sách: " + err.message;
    }
  }

  function closeReview() {
    stopReviewVideo();
    releaseVideo(review.video);
    Object.assign(review, { jobId: null, cues: [], video: null });
    review.dirty.clear();
    review.rows.clear();
    $("review-editor").replaceChildren();
    $("review-editor").classList.add("hidden");
    $("review-list-view").classList.remove("hidden");
    loadReviewList();
  }

  async function openReview(jobId) {
    let data;
    try { data = await api(`/jobs/${jobId}/cues`); }
    catch (err) { $("review-message").textContent = err.message; return; }
    Object.assign(review, { jobId, cues: data.cues });
    review.dirty.clear();
    review.rows.clear();

    const editor = $("review-editor");
    editor.replaceChildren();
    const video = el("video", { controls: "", preload: "metadata", src: `${API}/jobs/${jobId}/preview` });
    review.video = video;
    const counter = el("span", { class: "muted", id: "review-counter" });
    const status = el("span", { class: "status", id: "review-status" });
    const onlyEmpty = el("input", { type: "checkbox" });
    const back = el("button", { class: "small", text: "← Danh sách" });
    const save = el("button", { class: "small", text: "Lưu nháp" });
    const approve = el("button", { class: "small primary", text: "Duyệt và tiếp tục" });
    back.addEventListener("click", closeReview);
    save.addEventListener("click", () => saveReview());
    approve.addEventListener("click", approveReview);
    if (!data.editable) { save.disabled = true; approve.disabled = true; }

    editor.appendChild(el("div", { class: "review-top" }, [
      video,
      el("div", { class: "review-bar" }, [
        back, el("strong", { text: data.job.title }), counter,
        el("label", { class: "inline-check" }, [onlyEmpty, document.createTextNode("Chỉ hiện câu chưa có bản dịch")]),
        el("span", { class: "spacer" }), status, save, approve,
      ]),
    ]));

    const body = el("tbody");
    data.cues.forEach((cue) => {
      const jump = el("button", { class: "link", text: `${formatClock(cue.start_ms)} – ${formatClock(cue.end_ms)}`,
        title: "Phát từ câu này" });
      jump.addEventListener("click", () => { video.currentTime = cue.start_ms / 1000; video.play().catch(() => {}); });
      const input = el("textarea", { rows: "2", maxlength: "1000" });
      input.value = cue.vi_text;
      input.disabled = !data.editable;
      const row = el("tr", {}, [
        el("td", { class: "time" }, [jump]),
        el("td", { class: "source", text: cue.source_text }),
        el("td", {}, [input]),
      ]);
      input.addEventListener("input", () => {
        if (input.value.trim() === cue.vi_text.trim()) review.dirty.delete(cue.idx);
        else review.dirty.set(cue.idx, input.value);
        row.classList.toggle("dirty", review.dirty.has(cue.idx));
        row.classList.toggle("empty", !input.value.trim());
        updateReviewCounter();
      });
      row.classList.toggle("empty", !cue.vi_text.trim());
      review.rows.set(cue.idx, { row, input, cue });
      body.appendChild(row);
    });
    onlyEmpty.addEventListener("change", () => review.rows.forEach(({ row, input }) =>
      row.classList.toggle("hidden", onlyEmpty.checked && Boolean(input.value.trim()))));
    video.addEventListener("timeupdate", () => {
      const now = video.currentTime * 1000;
      review.rows.forEach(({ row, cue }) => row.classList.toggle("playing", now >= cue.start_ms && now < cue.end_ms));
    });
    const table = el("table", { class: "cue-table" }, [
      el("thead", {}, [el("tr", {}, [el("th", { text: "Thời gian" }),
        el("th", { text: data.source_lang ? `Phụ đề gốc (${data.source_lang})` : "Phụ đề gốc" }),
        el("th", { text: "Tiếng Việt" })])]),
      body,
    ]);
    editor.appendChild(el("div", { class: "table-wrap" }, [table]));
    updateReviewCounter();
    $("review-list-view").classList.add("hidden");
    editor.classList.remove("hidden");
  }

  function updateReviewCounter() {
    let empty = 0;
    review.rows.forEach(({ input }) => { if (!input.value.trim()) empty += 1; });
    const parts = [`${review.rows.size} câu`];
    if (empty) parts.push(`${empty} câu chưa có bản dịch`);
    if (review.dirty.size) parts.push(`${review.dirty.size} câu chưa lưu`);
    const counter = $("review-counter");
    if (counter) counter.textContent = parts.join(" · ");
  }

  async function saveReview() {
    const status = $("review-status");
    if (!review.dirty.size) { status.textContent = "Không có thay đổi cần lưu."; return true; }
    const cues = [...review.dirty].map(([idx, vi_text]) => ({ idx, vi_text }));
    try {
      await api(`/jobs/${review.jobId}/cues`, { method: "PUT", body: JSON.stringify({ cues }) });
      cues.forEach(({ idx, vi_text }) => {
        const entry = review.rows.get(idx);
        entry.cue.vi_text = vi_text.trim();
        entry.row.classList.remove("dirty");
      });
      review.dirty.clear();
      status.textContent = `Đã lưu ${cues.length} câu.`;
      updateReviewCounter();
      return true;
    } catch (err) {
      status.textContent = "Không lưu được: " + err.message;
      return false;
    }
  }

  /* Ngắt hẳn kết nối tải video để máy chủ không còn giữ file (Windows không cho chuyển file đang mở). */
  function releaseVideo(video) {
    if (!video) return;
    video.pause();
    video.removeAttribute("src");
    video.querySelectorAll("track").forEach((track) => track.remove());
    video.load();
  }

  async function approveReview() {
    if (!(await saveReview())) return;
    const jobId = review.jobId;
    const resumeAt = review.video ? review.video.currentTime : 0;
    releaseVideo(review.video);                       // nhả video TRƯỚC khi job chuyển file vào thư viện
    try {
      await api(`/jobs/${jobId}/approve`, { method: "POST" });
      closeReview();
      switchTab("queue");
    } catch (err) {
      $("review-status").textContent = "Chưa duyệt được: " + err.message;
      if (review.video) { review.video.src = `${API}/jobs/${jobId}/preview`; review.video.currentTime = resumeAt; }
    }
  }

  // ── Thư viện ───────────────────────────────────────────────────────────────
  const formatBytes = (bytes) => {
    if (!bytes) return "0 MB";
    const mb = bytes / 1048576;
    return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
  };

  function fillSelect(select, firstLabel, options) {
    const current = select.value;
    select.replaceChildren(el("option", { value: "", text: firstLabel }));
    options.forEach(([value, label]) => select.appendChild(el("option", { value: String(value), text: label })));
    select.value = [...select.options].some((o) => o.value === current) ? current : "";
  }

  let knownSeries = [], knownTags = [];
  async function loadLibraryFilters() {
    try {
      const [{ series }, { tags }] = await Promise.all([api("/series"), api("/tags")]);
      knownSeries = series; knownTags = tags;
      fillSelect($("lib-series"), "Mọi series", series.map((s) => [s.id, `${s.name} (${s.item_count})`]));
      fillSelect($("lib-tag"), "Mọi tag", tags.map((t) => [t.name, `${t.name} (${t.item_count})`]));
    } catch (err) {
      $("library-message").textContent = err.message;
    }
  }

  async function loadLibrary() {
    const grid = $("library-grid");
    const params = new URLSearchParams();
    const filters = { q: $("lib-q").value.trim(), series: $("lib-series").value, tag: $("lib-tag").value,
      status: $("lib-status").value, sort: $("lib-sort").value };
    Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); });
    const filtered = Boolean(filters.q || filters.series || filters.tag || filters.status);
    try {
      const { items } = await api("/library?" + params.toString());
      grid.replaceChildren();
      $("library-message").textContent = items.length ? `${items.length} video`
        : filtered ? "Không có video nào khớp bộ lọc." : "Thư viện đang trống.";
      items.forEach((item) => {
        const card = el("button", { class: "lib-card" });
        if (item.has_thumb) card.appendChild(el("img", { class: "lib-thumb", alt: "", loading: "lazy",
          src: `${API}/library/${item.id}/thumbnail` }));
        else card.appendChild(el("div", { class: "lib-thumb" }));
        const chips = el("div", { class: "chips" });
        if (item.series) chips.appendChild(el("span", { class: "chip series", text: item.series }));
        item.tags.forEach((tag) => chips.appendChild(el("span", { class: "chip", text: "#" + tag })));
        card.appendChild(el("div", { class: "lib-body" }, [
          el("div", { class: "lib-title", text: item.title }),
          el("div", { class: "muted", text: [item.episode_label, formatDuration(item.duration_s), item.quality,
            formatBytes(item.size_bytes)].filter(Boolean).join(" · ") }),
          el("span", { class: item.dubbed ? "badge ok" : "badge info", text: item.dubbed ? "Đã lồng tiếng" : "Chưa lồng tiếng" }),
          chips,
        ]));
        card.addEventListener("click", () => openPlayer(item.id));
        grid.appendChild(card);
      });
    } catch (err) {
      $("library-message").textContent = "Không tải được thư viện: " + err.message;
    }
  }

  function renderEditForm(item) {
    const title = el("input", { type: "text", maxlength: "200" });
    title.value = item.title;
    const note = el("textarea", { rows: "2", maxlength: "2000", placeholder: "Ghi chú riêng của bạn" });
    note.value = item.note;
    const series = el("input", { type: "text", maxlength: "80", list: "series-options", placeholder: "Để trống nếu không thuộc series nào" });
    series.value = item.series || "";
    const tags = el("input", { type: "text", list: "tag-options", placeholder: "Cách nhau bằng dấu phẩy, ví dụ: anime, xem lại" });
    tags.value = item.tags.join(", ");
    const seriesOptions = el("datalist", { id: "series-options" }, knownSeries.map((s) => el("option", { value: s.name })));
    const tagOptions = el("datalist", { id: "tag-options" }, knownTags.map((t) => el("option", { value: t.name })));
    const message = el("span", { class: "status" });
    const save = el("button", { class: "small primary", text: "Lưu thông tin" });
    save.addEventListener("click", async () => {
      save.disabled = true;
      try {
        const updated = await api(`/library/${item.id}`, { method: "PATCH", body: JSON.stringify({
          title: title.value, note: note.value, series: series.value,
          tags: tags.value.split(",").map((t) => t.trim()).filter(Boolean),
        }) });
        title.value = updated.title; series.value = updated.series || ""; tags.value = updated.tags.join(", ");
        const heading = $("player-view").querySelector("h2");
        if (heading) heading.textContent = updated.title;
        message.textContent = "Đã lưu.";
        loadLibraryFilters();
      } catch (err) {
        message.textContent = "Không lưu được: " + err.message;
      } finally {
        save.disabled = false;
      }
    });
    return el("div", { class: "edit-form" }, [
      el("label", {}, [document.createTextNode("Tên video"), title]),
      el("label", {}, [document.createTextNode("Series"), series]),
      el("label", {}, [document.createTextNode("Tag"), tags]),
      el("label", {}, [document.createTextNode("Ghi chú"), note]),
      el("div", { class: "row" }, [save, message]),
      seriesOptions, tagOptions,
    ]);
  }

  function closePlayer() {
    const view = $("player-view");
    const video = view.querySelector("video");
    releaseVideo(video);
    view.replaceChildren();
    view.classList.add("hidden");
    $("library-list-view").classList.remove("hidden");
  }

  async function openPlayer(itemId) {
    let item;
    try { item = await api(`/library/${itemId}`); }
    catch (err) { $("library-message").textContent = err.message; return; }
    const view = $("player-view");
    view.replaceChildren();
    const base = `${API}/library/${item.id}`;

    const back = el("button", { class: "small", text: "← Thư viện" });
    back.addEventListener("click", () => { closePlayer(); loadLibraryFilters().then(loadLibrary); });
    const remove = confirmButton("Xóa video", "Bấm lần nữa để xóa vĩnh viễn", async () => {
      closePlayer();                                  // nhả video trước khi xóa file
      try { await api(`/library/${item.id}`, { method: "DELETE" }); }
      catch (err) { $("library-message").textContent = "Chưa xóa được: " + err.message; }
      loadLibrary();
    });
    const video = el("video", { controls: "", preload: "metadata", src: base + "/stream" });
    const actions = el("div", { class: "job-actions" });
    if (item.has_source) {
      // Giữ video gốc: cho đổi qua lại giữa bản lồng tiếng và bản gốc, giữ nguyên vị trí đang xem.
      let showingSource = false;
      const toggle = el("button", { class: "small", text: "Xem bản gốc" });
      toggle.addEventListener("click", () => {
        const at = video.currentTime, wasPlaying = !video.paused;
        showingSource = !showingSource;
        video.src = base + "/stream" + (showingSource ? "?kind=source" : "");
        video.addEventListener("loadedmetadata", () => {
          video.currentTime = at;
          if (wasPlaying) video.play().catch(() => {});
        }, { once: true });
        toggle.textContent = showingSource ? "Xem bản lồng tiếng" : "Xem bản gốc";
      });
      actions.appendChild(toggle);
    }
    actions.appendChild(el("a", { class: "button", href: base + "/download",
      text: item.dubbed ? "Tải bản lồng tiếng" : "Tải xuống" }));
    if (item.has_source) actions.appendChild(el("a", { class: "button", href: base + "/download?kind=source", text: "Tải bản gốc" }));
    actions.appendChild(remove);
    view.appendChild(el("div", { class: "player-head" }, [back, actions]));

    if (item.has_sub_vi) {
      video.appendChild(el("track", { kind: "subtitles", src: base + "/subtitle?kind=vi", srclang: "vi",
        label: "Tiếng Việt", default: "" }));
    }
    if (item.has_sub_orig) {
      const lang = item.sub_orig_lang || "und";
      const track = el("track", { kind: "subtitles", src: base + "/subtitle?kind=orig", srclang: lang,
        label: `Phụ đề gốc (${lang})` });
      if (!item.has_sub_vi && lang.toLowerCase().startsWith("vi")) track.setAttribute("default", "");
      video.appendChild(track);
    }
    view.appendChild(el("div", { class: "player" }, [video]));
    view.appendChild(el("h2", { text: item.title }));
    const VOICES = { "vi-VN-HoaiMyNeural": "giọng Hoài My", "vi-VN-NamMinhNeural": "giọng Nam Minh" };
    view.appendChild(el("div", { class: "muted", text: [item.episode_label, formatDuration(item.duration_s), item.quality,
      item.dubbed ? `Đã lồng tiếng (${VOICES[item.voice] || item.voice})` : "Chưa lồng tiếng"].filter(Boolean).join(" · ") }));
    view.appendChild(renderEditForm(item));
    if (!item.browser_playable) view.appendChild(el("div", { class: "notice",
      text: "Định dạng này có thể không phát được trong trình duyệt. Nếu màn hình đen, hãy bấm Tải xuống và mở bằng trình phát trên máy." }));
    $("library-list-view").classList.add("hidden");
    view.classList.remove("hidden");
  }

  // ── Cài đặt: mặc định khi tạo mới ───────────────────────────────────────────
  const WHISPER_LABELS = { tiny: "tiny (nhanh nhất, kém nhất)", base: "base", small: "small (khuyên dùng)",
    medium: "medium (chậm, chính xác hơn)", "large-v3": "large-v3 (rất chậm trên CPU)" };

  function applyDefaultsToCreateTab(d) {
    $("opt-voice").value = d.default_voice;
    $("opt-orig").value = Math.round(d.default_orig_vol * 100);
    $("opt-dub").value = Math.round(d.default_dub_vol * 100);
    $("opt-keep").checked = d.default_keep_source;
    $("opt-orig-val").textContent = $("opt-orig").value + "%";
    $("opt-dub-val").textContent = $("opt-dub").value + "%";
  }

  function showDefaults(d) {
    $("set-whisper").replaceChildren(...d.whisper_models.map((m) => el("option", { value: m, text: WHISPER_LABELS[m] || m })));
    $("set-voice").value = d.default_voice;
    $("set-whisper").value = d.whisper_model;
    $("set-orig").value = Math.round(d.default_orig_vol * 100);
    $("set-dub").value = Math.round(d.default_dub_vol * 100);
    $("set-keep").checked = d.default_keep_source;
    $("set-orig-val").textContent = $("set-orig").value + "%";
    $("set-dub-val").textContent = $("set-dub").value + "%";
  }

  async function loadDefaults(alsoCreateTab) {
    try {
      const d = await api("/settings");
      showDefaults(d);
      if (alsoCreateTab) applyDefaultsToCreateTab(d);
    } catch (err) { $("set-message").textContent = err.message; }
  }

  async function saveDefaults() {
    try {
      const d = await api("/settings", { method: "PUT", body: JSON.stringify({
        default_voice: $("set-voice").value, whisper_model: $("set-whisper").value,
        default_orig_vol: Number($("set-orig").value) / 100, default_dub_vol: Number($("set-dub").value) / 100,
        default_keep_source: $("set-keep").checked,
      }) });
      showDefaults(d);
      if (!state.scan) applyDefaultsToCreateTab(d);      // đang chọn dở ở tab Tạo mới thì không ghi đè
      $("set-message").textContent = "Đã lưu.";
    } catch (err) { $("set-message").textContent = "Không lưu được: " + err.message; }
  }

  // ── Cài đặt: nơi lưu và dung lượng ─────────────────────────────────────────
  let storageTimer = null;

  function stat(label, value, extraClass) {
    return el("div", { class: "stat" + (extraClass ? " " + extraClass : "") }, [
      el("div", { class: "stat-label", text: label }),
      el("div", { class: "stat-value" + (extraClass === "span" ? " path" : ""), text: value }),
    ]);
  }

  async function loadStorage() {
    clearTimeout(storageTimer);
    let data;
    try { data = await api("/storage"); }
    catch (err) { $("storage-message").textContent = err.message; return; }
    $("storage-summary").replaceChildren(
      stat("Thư mục thư viện" + (data.is_default_root ? " (mặc định)" : ""), data.library_root, "span"),
      stat("Số video", String(data.item_count)),
      stat("Thư viện đang dùng", formatBytes(data.library_bytes)),
      stat("File tạm", formatBytes(data.work_bytes)),
      stat("Ổ đĩa còn trống", formatBytes(data.disk_free_bytes)),
    );

    const move = data.move || {};
    const moving = move.status === "running";
    if (moving) $("storage-message").textContent = `Đang chuyển thư viện: ${move.done}/${move.total} video…`;
    else if (move.status === "done") $("storage-message").textContent = move.leftover && move.leftover.length
      ? `Đã chuyển xong. ${move.leftover.length} thư mục cũ chưa xóa được vì đang bị giữ; hãy dọn sau.`
      : "Đã chuyển xong thư viện sang nơi mới.";
    else if (move.status === "failed") $("storage-message").textContent = "Chuyển thất bại, thư viện vẫn ở nơi cũ: " + move.error;
    const moveButton = confirmButton("Chuyển thư viện", "Bấm lần nữa để bắt đầu chuyển", startMove);
    moveButton.classList.remove("danger");
    moveButton.disabled = moving;
    $("storage-move-slot").replaceChildren(moveButton);

    const list = $("cleanup-list");
    const checked = new Set([...list.querySelectorAll("input:checked")].map((i) => i.value));
    list.replaceChildren();
    Object.entries(data.cleanable).forEach(([name, info]) => {
      const box = el("input", { type: "checkbox", value: name });
      box.disabled = info.count === 0;
      box.checked = checked.has(name) && info.count > 0;
      list.appendChild(el("label", { class: "check-row" }, [
        box, document.createTextNode(info.label),
        el("span", { class: "muted", text: info.count ? `${info.count} mục · ${formatBytes(info.bytes)}` : "không có" }),
      ]));
    });
    $("cleanup-slot").replaceChildren(confirmButton("Dọn các mục đã chọn", "Bấm lần nữa để xóa vĩnh viễn", runCleanup));
    if (moving && activeTab === "settings") storageTimer = setTimeout(loadStorage, 1500);
  }

  async function startMove() {
    try {
      await api("/storage/root", { method: "PUT", body: JSON.stringify({ path: $("storage-path").value }) });
      $("storage-path").value = "";
    } catch (err) {
      $("storage-message").textContent = "Không chuyển được: " + err.message;
      const button = confirmButton("Chuyển thư viện", "Bấm lần nữa để bắt đầu chuyển", startMove);
      button.classList.remove("danger");
      $("storage-move-slot").replaceChildren(button);
      return;
    }
    loadStorage();
  }

  async function runCleanup() {
    const targets = [...$("cleanup-list").querySelectorAll("input:checked")].map((i) => i.value);
    if (!targets.length) { $("cleanup-message").textContent = "Hãy chọn ít nhất một mục."; loadStorage(); return; }
    try {
      const result = await api("/storage/cleanup", { method: "POST", body: JSON.stringify({ targets }) });
      $("cleanup-message").textContent = `Đã giải phóng ${formatBytes(result.freed_bytes)}.`
        + (result.skipped_busy ? ` ${result.skipped_busy} mục đang bị giữ nên chưa xóa được.` : "");
    } catch (err) { $("cleanup-message").textContent = "Không dọn được: " + err.message; }
    loadStorage();
  }

  // ── Cài đặt: series và tag ─────────────────────────────────────────────────
  async function loadTaxonomy() {
    try {
      const [{ series }, { tags }] = await Promise.all([api("/series"), api("/tags")]);
      knownSeries = series; knownTags = tags;
      renderTaxonomy($("series-list"), series, "series", true);
      renderTaxonomy($("tag-list"), tags, "tags", false);
    } catch (err) { $("taxonomy-message").textContent = err.message; }
  }

  function renderTaxonomy(box, rows, path, renamable) {
    box.replaceChildren();
    if (!rows.length) { box.appendChild(el("p", { class: "placeholder", text: "Chưa có." })); return; }
    rows.forEach((row) => {
      const line = el("div", { class: "tax-row" });
      const name = el("span", { class: "name", text: row.name });
      const count = el("span", { class: "muted", text: `${row.item_count} video` });
      const remove = confirmButton("Xóa", "Xóa (video được giữ lại)", async () => {
        try { await api(`/${path}/${row.id}`, { method: "DELETE" }); }
        catch (err) { $("taxonomy-message").textContent = err.message; }
        loadTaxonomy();
      });
      line.append(name, count);
      if (renamable) {
        const rename = el("button", { class: "small", text: "Đổi tên" });
        rename.addEventListener("click", () => {
          const input = el("input", { type: "text", maxlength: "80" });
          input.value = row.name;
          const ok = el("button", { class: "small primary", text: "Lưu" });
          ok.addEventListener("click", async () => {
            try {
              await api(`/${path}/${row.id}`, { method: "PATCH", body: JSON.stringify({ name: input.value }) });
              $("taxonomy-message").textContent = "";
            } catch (err) { $("taxonomy-message").textContent = "Không đổi được tên: " + err.message; }
            loadTaxonomy();
          });
          line.replaceChildren(input, ok);
          input.focus();
        });
        line.appendChild(rename);
      }
      line.appendChild(remove);
      box.appendChild(line);
    });
  }

  // ── Cài đặt: cookie ────────────────────────────────────────────────────────
  function showCookieStatus(status) {
    const box = $("cookie-status");
    if (!status.configured) {
      box.className = "notice";
      box.textContent = "Chưa lưu cookie nào.";
      return;
    }
    const parts = [`Đã lưu ${status.cookie_count} cookie cho ${status.sites.join(", ")}.`];
    if (!status.has_login_cookie) parts.push("Không thấy cookie SESSDATA, có thể bạn chưa đăng nhập lúc lấy cookie.");
    if (status.expired) parts.push("Cookie đã hết hạn, hãy lấy lại.");
    else if (status.expires_at) parts.push("Hết hạn ngày " + new Date(status.expires_at * 1000).toLocaleDateString("vi-VN") + ".");
    const bad = status.expired || !status.has_login_cookie;
    box.className = "notice" + (bad ? "" : " ok");
    box.textContent = parts.join(" ");
  }

  async function loadCookieStatus() {
    try { showCookieStatus(await api("/settings/cookie")); }
    catch (err) { $("cookie-message").textContent = err.message; }
  }

  async function saveCookie() {
    const text = $("cookie-text").value;
    if (!text.trim()) { $("cookie-message").textContent = "Hãy dán nội dung cookie trước."; return; }
    $("cookie-save").disabled = true;
    try {
      const status = await api("/settings/cookie", {
        method: "PUT", body: JSON.stringify({ text, site: $("cookie-site").value }),
      });
      $("cookie-text").value = "";
      $("cookie-message").textContent = "Đã lưu. Quay lại tab Tạo mới và quét lại link.";
      showCookieStatus(status);
      loadHealth();
    } catch (err) {
      $("cookie-message").textContent = "Không lưu được: " + err.message;
    } finally {
      $("cookie-save").disabled = false;
    }
  }

  async function deleteCookie() {
    try {
      showCookieStatus(await api("/settings/cookie", { method: "DELETE" }));
      $("cookie-message").textContent = "Đã xóa cookie.";
      loadHealth();
    } catch (err) {
      $("cookie-message").textContent = err.message;
    }
  }

  // ── Khởi động ──────────────────────────────────────────────────────────────
  $("scan-btn").addEventListener("click", runScan);
  $("start-btn").addEventListener("click", startJobs);
  $("opt-orig").addEventListener("input", (e) => { $("opt-orig-val").textContent = e.target.value + "%"; });
  $("opt-dub").addEventListener("input", (e) => { $("opt-dub-val").textContent = e.target.value + "%"; });
  let searchTimer = null;
  $("lib-q").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadLibrary, 250); });
  ["lib-series", "lib-tag", "lib-status", "lib-sort"].forEach((id) => $(id).addEventListener("change", loadLibrary));
  $("set-save").addEventListener("click", saveDefaults);
  $("set-orig").addEventListener("input", (e) => { $("set-orig-val").textContent = e.target.value + "%"; });
  $("set-dub").addEventListener("input", (e) => { $("set-dub-val").textContent = e.target.value + "%"; });
  $("queue-clear").addEventListener("click", async () => {
    try {
      const result = await api("/jobs/clear-finished", { method: "POST" });
      $("queue-message").textContent = `Đã dọn ${result.deleted} job. Video vẫn còn trong Thư viện.`;
    } catch (err) { $("queue-message").textContent = err.message; }
    loadJobs();
  });
  $("cookie-check").addEventListener("click", async () => {
    $("cookie-check").disabled = true;
    $("cookie-message").textContent = "Đang hỏi máy chủ Bilibili…";
    try { $("cookie-message").textContent = (await api("/settings/cookie/check", { method: "POST" })).message; }
    catch (err) { $("cookie-message").textContent = err.message; }
    $("cookie-check").disabled = false;
  });
  $("cookie-save").addEventListener("click", saveCookie);
  $("cookie-delete").addEventListener("click", deleteCookie);
  loadHealth();
  loadCookieStatus();
  loadDefaults(true);
})();
