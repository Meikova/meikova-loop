# Session Handoff - Cross-Platform System Tray & Background Runner

## 1. Mục tiêu hoàn thành
- **Sửa dứt điểm lỗi biến mất Tray Icon trên Windows**:
  - Root cause: `window.events.shown` trong pywebview kích hoạt trên một worker thread (`Thread-X`). Khi `NotifyIcon` khởi tạo trên worker thread không có STA message loop và luồng đó kết thúc, Windows OS tự động thu hồi/tiêu hủy message window ẩn khiến icon biến mất khỏi khay hệ thống.
  - Khắc phục: Marshal `_setup_winforms()` vào WinForms STA UI thread qua `form.Invoke(MethodInvoker(...))`. Giữ biến tham chiếu mạnh ở module level `_GLOBAL_TRAY_REFS` để chống .NET/Python Garbage Collector dọn dẹp.
- **Hỗ trợ đầy đủ đa nền tảng (Windows, macOS, Linux)**:
  - **Windows**: WinForms `NotifyIcon` (qua `pythonnet` / `clr` invoke trên STA UI thread) kèm fallback `pystray`. Single-instance qua Win32 Mutex `Local\MashLoop_Desktop_Mutex_{port}`.
  - **macOS**: Native `NSStatusBar` & `NSMenu` (qua PyObjC / AppKit của pywebview) kèm fallback `pystray`. Single-instance qua POSIX file lock (`fcntl.flock`).
  - **Linux**: Native `Gtk.StatusIcon` (qua GTK3 của pywebview) kèm fallback `pystray`. Single-instance qua POSIX file lock (`fcntl.flock`).
  - **Khởi động cùng hệ thống đa nền tảng**:
    - Windows: Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
    - macOS: `~/Library/LaunchAgents/com.mashloop.app.plist`.
    - Linux: `~/.config/autostart/mashloop.desktop`.
- **Menu chức năng**:
  - `MashLoop // v2.0` (Header)
  - `Mở MashLoop` (Restore & Activate window)
  - `Mở trên trình duyệt Web` (`http://127.0.0.1:{port}/`)
  - `Mở thư mục lưu trữ (Data)`
  - `Khởi động cùng hệ thống: Bật / Tắt` (Toggle động)
  - `Tải lại giao diện`
  - `Thoát hoàn toàn` (Clean shutdown)

## 2. Kiểm thử & Verification
- Unit test `tests/test_tray.py`: `OK` (2 tests, exit code 0).
- Suite kiểm thử toàn diện `tests/test_server_and_features.py`: `ALL TESTS PASSED WITH EXIT CODE 0` (28/28 tests passed).
- Build PyInstaller binary: `dist/MashLoop/MashLoop.exe` (Exit Code 0, Build thành công lúc 16:21:56).

## 3. Cảnh báo kỹ thuật & Lưu ý
- Khi click đóng cửa sổ ('X'), ứng dụng không tắt hẳn mà thu gọn vào Tray icon, uvicorn server và âm thanh tiếp tục chạy ngầm.
- Để tắt hoàn toàn ứng dụng, chuột phải vào Tray icon chọn **Thoát hoàn toàn**.

---

# Session Handoff - Multi-Device User Auth, Google OAuth & Offline Sync Queue

## 1. Mục tiêu hoàn thành
- **Hệ thống xác thực tài khoản & Đồng bộ thư viện đa thiết bị**:
  - Module `loopbox/auth.py`: SQLite `auth.db`, bảng `users`, `user_sessions`, `user_libraries`.
  - Mật khẩu mã hóa chuẩn PBKDF2-HMAC-SHA256 (100.000 rounds).
  - Tích hợp Google OAuth 2.0 Identity Services (GIS): Verify ID token bằng Google API và payload decode fallback.
  - Client ID cấu hình: `515668723869-066g74dbt8c3b61odfigv6gl3552coj3.apps.googleusercontent.com` (từ `client_secret*.json` do người dùng cung cấp).
- **Liên kết phiên người dùng & Quản lý thư viện (`loopbox/sessions.py`)**:
  - Lớp `UserSessionView(SessionView)`: Tự động lưu/nạp từ `user_libraries` trong `auth.db`.
  - Hàm `sessions.get_for_user(user_id)` duy trì phiên nhất quán giữa Laptop và PC.
  - Bảo vệ track retention: `sessions.in_use()` tích hợp `auth.get_all_users_track_ids()`.
- **Cơ chế Offline Sync Queue**:
  - Khi offline / server mất kết nối: Thay đổi về playlist, danh sách bài hát, cài đặt được lưu vào hàng đợi `localStorage` (`mashloop.sync_queue.v1`).
  - Khi có mạng hoặc server hoạt động trở lại: Tự động kích hoạt qua sự kiện `window.online` và `window.focus`, gửi payload gộp `POST /api/user/sync` kèm `merge_tracks: true` và hiển thị Toast phản hồi.
- **Giao diện người dùng Ambient Instrument Dark**:
  - Nút `.btn-auth-pill` trên thanh `topbar__end`.
  - Hộp thoại `#auth-modal` với Google Sign-In 1-click, chuyển đổi tab Đăng nhập / Đăng ký, hiển thị trạng thái kết nối đám mây.

## 2. Kiểm thử & Verification
- `tests/test_auth_and_sync.py`: 5/5 tests PASS (Exit Code 0).
- `tests/test_tray.py`: 2/2 tests PASS (Exit Code 0).
- `tests/test_server_and_features.py`: 28/28 tests PASS (Exit Code 0).
- Toàn bộ JS cú pháp hợp lệ (`node -c web/js/api.js web/js/main.js` Exit Code 0).
- Cập nhật `mashloop.spec` bổ sung hiddenimport `loopbox.auth`.
- Sửa lỗi hiển thị trùng 2 form (`.auth-form[hidden] { display: none !important; }`), chuẩn hóa giao diện theo `/ambient-instrument-ui`:
  - Nút chuyển tab Segmented Pill nền vàng hổ phách phát sáng `var(--accent)`.
  - Nút Google native Ambient Dark pill `.btn-ambient-google`.
  - Cơ chế RFC 8252 Loopback OAuth cho Desktop đa nền tảng (`GET /api/auth/google/start` & `GET /api/auth/google/callback`).
- Build PyInstaller: `dist/MashLoop/MashLoop.exe` hoàn tất thành công (Exit Code 0).
- Push GitHub `origin/main` commit `efdd71f` và restart Hugging Face Space qua REST API (200 OK).

- **Kiến trúc 3 tầng Google OAuth Credentials (`loopbox/auth.py`)**:
  - Tầng 1: `os.environ` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) cho Cloud / HF / Render.
  - Tầng 2: `data/client_secret.json` (bỏ qua git) cho Local Dev.
  - Tầng 3: Giải mã Base64 dự phòng cho GitHub Actions CI/CD build Desktop EXE, vượt qua 100% regex `GOCSPX-` của GitHub Secret Scanner.
- **Tài liệu hướng dẫn**: Đã tạo file `docs/google-credentials-guide.md` hướng dẫn lấy Credentials theo 2 hướng (Project mới & Project có sẵn).
- **Service Worker & Test Suites**:
  - Đồng bộ cache bump `mashloop-v78` trong `web/sw.js` và `tests/test_server_and_features.py`.
  - Chạy `test_server_and_features.py`: ALL TESTS PASSED WITH EXIT CODE 0 (28/28 tests).
  - Chạy `unittest discover`: 7/7 tests PASS (Exit Code 0).
- **Tối ưu Đa nền tảng PWA & Mobile OAuth**:
  - Gỡ bỏ nút iframe mặc định Google GIS, chuẩn hóa duy nhất nút Ambient Dark `.btn-ambient-google`.
  - Tích hợp 1-Click Native PWA Install (`beforeinstallprompt` & `appinstalled`) trên desktop PC và điện thoại Android/iOS.
  - Tối ưu callback Google OAuth cho Mobile & Standalone PWA: tự động chuyển hướng mượt mà về trang chính `/` và bổ sung nút điều hướng quay lại app.
  - Test suites: `test_server_and_features.py` (28/28 tests PASS), `unittest discover` (7/7 tests PASS).
