// =============================================================================
// background.js – Service Worker (Tổng đài trung chuyển tin nhắn)
// =============================================================================
//
// LUỒNG HOẠT ĐỘNG:
//
//   [Top Window - content.js]
//        │  chrome.runtime.sendMessage({ action: "START_DUBBING_COMMAND" })
//        ▼
//   [background.js]   ← file này
//        │  chrome.tabs.sendMessage(tabId, { action: "EXECUTE_DUBBING" })
//        ▼
//   [Tất cả iframe trong tab - content.js]
//        │  document.querySelector('video') → chạy dubbing pipeline
//        ▼
//   [Video element bên trong iframe Coursera]
//
// Lý do cần background làm trung gian:
//   - Top window KHÔNG thể gọi chrome.tabs.sendMessage tới chính nó.
//   - Chỉ có Extension context (background) mới được dùng chrome.tabs API.
//   - Background nhận message → biết được tabId của sender → broadcast lại.
// =============================================================================

// ─── Lắng nghe toàn bộ message từ content scripts ───────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

  // Log để debug – có thể xoá sau khi production
  console.log('[Background] Nhận message:', message.action, '| Tab:', sender.tab?.id);

  // ─── Xử lý lệnh BẮT ĐẦU lồng tiếng ──────────────────────────────────────
  if (message.action === 'START_DUBBING_COMMAND') {

    const tabId = sender.tab?.id;

    if (!tabId) {
      console.error('[Background] Không xác định được tabId. Bỏ qua.');
      sendResponse({ success: false, error: 'Không có tabId' });
      return;
    }

    // Broadcast lệnh EXECUTE_DUBBING xuống TẤT CẢ frame trong tab.
    // Khi manifest có "all_frames": true, Chrome đã inject content.js
    // vào mọi iframe → tất cả đều đang lắng nghe và sẽ nhận được lệnh này.
    chrome.tabs.sendMessage(
      tabId,
      {
        action:    'EXECUTE_DUBBING',
        // Truyền thêm config nếu cần (ngôn ngữ, tốc độ TTS, v.v.)
        config: message.config ?? {}
      },
      // frameId KHÔNG được set ở đây → Chrome broadcast tới mọi frame.
      // Nếu chỉ muốn gửi tới 1 iframe cụ thể, thêm: { frameId: <id> }
      (response) => {
        if (chrome.runtime.lastError) {
          // Lỗi thường gặp: tab đã đóng hoặc chưa có frame nào lắng nghe
          console.warn('[Background] sendMessage lỗi:', chrome.runtime.lastError.message);
        } else {
          console.log('[Background] Đã broadcast EXECUTE_DUBBING. Phản hồi:', response);
        }
      }
    );

    // Xác nhận đã nhận lệnh về phía người gửi (top window)
    sendResponse({ success: true, message: 'Đã broadcast EXECUTE_DUBBING tới tab ' + tabId });

  }

  // ─── Xử lý lệnh DỪNG lồng tiếng ──────────────────────────────────────────
  else if (message.action === 'STOP_DUBBING_COMMAND') {

    const tabId = sender.tab?.id;
    if (tabId) {
      chrome.tabs.sendMessage(tabId, { action: 'STOP_DUBBING' }, () => {
        if (chrome.runtime.lastError) {
          console.warn('[Background] STOP broadcast lỗi:', chrome.runtime.lastError.message);
        }
      });
    }
    sendResponse({ success: true });

  }

  // ─── Nhận báo cáo trạng thái từ iframe ────────────────────────────────────
  // Iframe gửi về để top window biết video đã được tìm thấy hay chưa
  else if (message.action === 'IFRAME_STATUS_REPORT') {

    const tabId = sender.tab?.id;
    console.log('[Background] Iframe báo cáo:', message.status, '| tabId:', tabId);

    // Chuyển tiếp trạng thái lên top window (frameId = 0 là top window)
    if (tabId) {
      chrome.tabs.sendMessage(
        tabId,
        {
          action: 'UPDATE_UI_STATUS',
          status: message.status,  // 'VIDEO_FOUND' | 'VIDEO_NOT_FOUND' | 'DUBBING_STARTED'
          data:   message.data ?? {}
        },
        { frameId: 0 },  // Chỉ gửi tới top frame (frameId: 0)
        () => { if (chrome.runtime.lastError) {} } // Suppress lỗi nếu top frame không lắng nghe
      );
    }

  }

  // Trả về true để giữ kênh message mở (cho async sendResponse)
  return true;
});

// ─── Xử lý khi extension được cài/update ────────────────────────────────────
chrome.runtime.onInstalled.addListener((details) => {
  console.log('[Background] Extension', details.reason === 'install' ? 'đã cài đặt' : 'đã cập nhật');
});
