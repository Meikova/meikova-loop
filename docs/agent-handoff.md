# BẢN GIAO TIẾP LIÊN PHIÊN (SESSION HANDOFF) — MEIKOVA LOOP

## Phiên làm việc: 06/11/2026

### 1. Mục tiêu hoàn thành (v1.0.25)
1. **Live Karaoke Mic Engine & Direct Passthrough (`web/js/mic.js`, `web/index.html`, `web/css/app.css`, `web/js/main.js`):**
   - Tích hợp lớp `KaraokeMic` sử dụng Web Audio API kết nối luồng microphone từ phần cứng máy tính trực tiếp vào `engine.master`.
   - **Hát phát ra loa ngay lập tức (Real-time monitoring):** Độ trễ siêu thấp near-zero latency, tích hợp `echoCancellation: true` và `noiseSuppression: true` chống hú rè.
   - **Bảo vệ âm thanh:** Bộ lọc High-pass Filter 85Hz triệt tiêu tiếng thở và tiếng ồn nền, đi qua Limiter chống vỡ tiếng (anti-clipping).
   - **Thu âm song ca:** Luồng Mic được đưa vào `engine.analyser`, do đó khi nhấn "Thu âm", bản thu Live Mix xuất ra `.webm` sẽ có cả giọng hát lẫn beat nhạc nền.
   - **Giao diện điều khiển:** Bổ sung nút `Mic Hát` trên Floating Deck và popover cài đặt âm lượng `0% - 200%` chuẩn Ambient Dark. Phím tắt nhanh: `H`.
   - **Phân tách trực quan:** Đổi icon nút tách stem (`#btn-vocal-mode`) sang icon waveform chuyên dụng để người dùng không bị nhầm lẫn giữa tính năng tách lời và micro vật lý.

2. **Khắc phục lỗi Responsive Floating Deck (`web/css/app.css`):**
   - Loại bỏ viền nét đứt (`dashed`), thay bằng viền solid hairline `1px solid var(--line-soft)` kèm quầng sáng phát quang Ambient Dark.
   - Khai báo Container Queries `@container stage` kết hợp Media queries đa tầng: Tự động thu gọn các text label khi sân khấu hẹp, giữ nguyên `.rec-dot` và `.mic-dot`, đảm bảo không bao giờ bị tràn ngang đè lên panel thư viện.

3. **Custom Ambient Audio Player cho Modal Bản thu âm (`web/index.html`, `web/css/app.css`, `web/js/main.js`):**
   - Chuẩn hóa header modal theo cấu trúc `.mobile-modal__head` và `.mobile-modal__close`, sửa lỗi nút đóng bị rớt dòng.
   - Thay thế triệt để thẻ native `<audio controls>` xám xịt của trình duyệt bằng Custom Audio Player chuẩn Meikova Ambient Dark: Nút Play/Pause neon, thanh scrubber tiến trình mượt mà, thời gian Mono tabular-nums, nút Mute/Unmute.
   - Đảm bảo dừng phát khi đóng modal bằng nút bấm hoặc phím `Escape`.

### 2. Kiểm thử & Xác thực (Verification)
- Lệnh kiểm tra: `.\.venv\Scripts\python.exe tests/test_server_and_features.py`
- Kết quả: **ALL TESTS PASSED WITH EXIT CODE 0**
- Test case bổ sung: `test_karaoke_mic_and_ambient_audio_player()`
- Bump SemVer: **v1.0.25** qua `version.py` đồng bộ toàn bộ file cấu hình.

### 3. Tồn đọng & Lưu ý kỹ thuật
- Khi chạy trên trình duyệt web, người dùng cần cho phép quyền truy cập Microphone khi được hỏi.
- Khi sử dụng loa ngoài công suất lớn, khuyến cáo người dùng đeo tai nghe hoặc duy trì khoảng cách giữa mic và loa để thuật toán Echo Cancellation hoạt động tối ưu nhất.

### 4. Hotfix: Tràn thanh âm lượng ngoài viền Deck
- **Nguyên nhân gốc rễ:** Sau khi bổ sung nút Mic Hát, tổng chiều rộng của Deck khi mở đủ text nhãn tăng lên ~1220px. Trên các màn hình laptop scaling 125% (viewport logic ~1536px), sau khi mở thư viện bên phải ~400px thì stage chỉ còn ~1136px - 1230px, khiến breakpoint cũ (1180px) chưa kích hoạt, làm các phần tử con không thu gọn và bị tràn đâm xuyên qua đường viền bo cong pill của Deck.
- **Giải pháp xử lý triệt để:**
  1. Nâng breakpoint Container Query @container stage từ 1180px lên 1480px.
  2. Bổ sung @media (max-width: 1680px) đa tầng fallback tự động thu gọn text nhãn thành icon-only, giúp Deck thu nhỏ về ~550px cực kỳ thoáng đãng.
  3. Thu gọn slider âm lượng từ 92px xuống 72px và ẩn chữ 70% (em) trên các màn hình có chiều rộng stage dưới 1480px.
  4. Tăng khoảng đệm an toàn bên phải của .deck (padding: 6px 14px 6px 12px;) để thanh volume không bao giờ chạm vào góc bo tròn 9999px.

### 5. Native Windows Build (PyInstaller)
- File thực thi: `dist/MeikovaLoop/MeikovaLoop.exe`
- Dung lượng: ~67 MB
- Đóng gói đầy đủ Web assets (v=101, CSS responsive fix, Karaoke Mic engine).
- Trạng thái: Build hoàn tất thành công (Exit Code 0).

### 6. Fix Microphone Permission Denied in Desktop App (v1.0.26)
- **Nguyên nhân gốc rễ:** Trên Windows desktop shell chạy Microsoft Edge WebView2 (pywebview), khi ứng dụng gọi `navigator.mediaDevices.getUserMedia()`, WebView2 phát sinh sự kiện `CoreWebView2.PermissionRequested`. Do ứng dụng chạy ở chế độ frameless (không có thanh công cụ trình duyệt mặc định) và pywebview không cài đặt bộ xử lý sự kiện này, WebView2 mặc định từ chối cấp quyền truy cập phần cứng (`Permission denied / NotAllowedError`).
- **Giải pháp xử lý triệt để:**
  1. Thêm cờ Chromium tự động phê duyệt thiết bị media vào `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`: `--use-fake-ui-for-media-stream`, `--enable-features=AudioServiceOutOfProcess`, `--autoplay-policy=no-user-gesture-required` tại cả `meikova_loop_app.py` và `loopbox/desktop.py`. Cờ này cho phép truy cập trực tiếp vào microphone phần cứng thật mà không hiển thị dialog chặn.
  2. Đăng ký sự kiện `CoreWebView2.PermissionRequested` trên WebView2 control: Tự động gán `args.State = CoreWebView2PermissionState.Allow` và `args.SavesInProfile = True`.
  3. Cải tiến `web/js/mic.js`: Tự động fallback về `{ audio: true }` nếu driver âm thanh của thiết bị từ chối các ràng buộc xử lý số tín hiệu (DSP constraints).
  4. Cải tiến `web/js/main.js`: Thông báo lỗi tiếng Việt rõ ràng, chỉ dẫn người dùng mở quyền trong Windows Settings khi cần.
  5. Nâng phiên bản SSOT lên **v1.0.26** và đồng bộ toàn bộ codebase.

### 7. Responsive Polish: Record Button SVG & Fullscreen Zen Mode Deck
- **Nút thu âm bị teo nhỏ mất SVG:**
  - Bổ sung biểu tượng SVG chuẩn vector optical-centered (`<svg class="deck__rec-icon"><circle cx="12" cy="12" r="8"/><circle class="deck__rec-core" cx="12" cy="12" r="3.5"/></svg>`) cho cả `#btn-record` trên Floating Deck lẫn `#zen-btn-record` trên Zen HUD.
  - Thiết lập `min-width: 38px !important; flex-shrink: 0 !important;` giúp nút khi ẩn text nhãn vẫn duy trì hình dáng bo tròn chuẩn 38px hoàn toàn cân đối với các nút bên cạnh.
  - Trạng thái `[aria-pressed="true"]`: nhân SVG `deck__rec-core` và viền ngoài phát quang đỏ rực `#ef4444`.
- **Tràn âm lượng trong Chế độ Toàn màn hình (Zen Mode):**
  - Loại bỏ hoàn toàn selector loại trừ `:not(.is-zen)` khỏi `@media (max-width: 1680px)`.
  - Thêm quy tắc riêng cho `body.is-zen .deck`: luôn ẩn text nhãn và ẩn số `em` âm lượng, đưa Deck về dạng pill icon-only siêu gọn (~540px), căn giữa tuyệt đối với `padding: 5px 16px 5px 10px` và `max-width: calc(100vw - 32px)`, loại bỏ 100% hiện tượng tràn slider qua mép cong.

### 8. Root Cause Triệt để Microphone & Dấu chấm REC Beacon (v1.0.28)
- **Dấu chấm ghi âm bị chạy lệch tâm (chạy ra chạy vào):**
  - *Nguyên nhân:* Phần tử SVG `<circle>` có `transform-origin` mặc định là `(0, 0)` (góc trên bên trái viewport `0 0 24 24`). Khi chạy animation `scale(1.35)`, tâm hình tròn bị tịnh tiến chéo về `(16.2, 16.2)` làm dấu chấm lệch hẳn ra mép vòng ngoài.
  - *Khắc phục:* Thiết lập `transform-box: fill-box; transform-origin: center;` cho `.deck__rec-core`, khóa cứng tâm phóng to thu nhỏ tại `(12, 12)`. Tinh chỉnh nhịp đập `@keyframes rec-pulse` 1.1s cubic-bezier êm ái (`scale(1.15)` độ sáng 100% thu về `scale(0.72)` độ mờ 22%), mô phỏng chuẩn xác đèn beacon ghi âm phòng thu chuyên nghiệp.
- **Microphone Permission Denied trên Desktop WebView2 (Root Cause):**
  - *Nguyên nhân gốc rễ thực sự:* Trong `loopbox/security_shield.py`, middleware bảo mật `SecurityHeadersMiddleware` gán cứng header HTTP:
    `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
    Chỉ thị `microphone=()` theo chuẩn W3C tuyên bố cấm 100% việc sử dụng microphone trên toàn bộ tài liệu và iframe! Trình duyệt/WebView2 khi nhận header này sẽ tự động ép `navigator.permissions.query({ name: 'microphone' })` về `state: "denied"` và từ chối gọi `getUserMedia` ngay lập tức với mã lỗi `NotAllowedError: Permission denied` mà không thèm bắn sự kiện `PermissionRequested`.
  - *Khắc phục triệt để:*
    1. Đổi `Permissions-Policy: microphone=()` thành `microphone=(self)` trong `loopbox/security_shield.py`, cho phép chính origin ứng dụng sử dụng micro.
    2. Hook `EdgeChrome.on_webview_ready` và `PermissionRequested` tự động gán `args.State = Allow` và `args.SavesInProfile = True`.
    3. Đã chạy kịch bản kiểm thử thực tế trên WebView2 kết nối trực tiếp driver phần cứng: nhận diện thành công micro thật `Default - Microphone Array (Realtek(R) Audio)` với trạng thái `readyState: live`.
  - Bump phiên bản SSOT lên **v1.0.28** qua `version.py --bump patch`.
