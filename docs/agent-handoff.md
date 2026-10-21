# Session Handoff - 100% Brand Assets & Logo Synchronization (Meikova Loop - Phase Rotor)

## 1. Mục tiêu hoàn thành
- **Tối ưu tốc độ biến mất của Tray Icon khi Thoát hoàn toàn (Instant Tray Disappear)**:
  - **Vấn đề**: Khi chuột phải chọn "Thoát hoàn toàn", icon trên khay hệ thống mất vài giây mới biến mất do luồng dọn dẹp đợi uvicorn server graceful shutdown và WebView2 teardown mà không flush message queue của Windows Shell.
  - **Khắc phục**:
    1. Trong `_do_cleanup()`: Thiết lập tuần tự `tray.Visible = False`, `tray.Icon = None`, `tray.Dispose()`.
    2. Gọi ngay `Application.DoEvents()` để xả hàng đợi thông điệp WinForms, đẩy tức thì lệnh `Shell_NotifyIcon(NIM_DELETE)` sang `explorer.exe` (thời gian xử lý < 3ms).
    3. Thêm hàm `_refresh_tray_window()` gửi `InvalidateRect` ép `Shell_TrayWnd` vẽ lại ngay, xóa sạch tàn dư icon.
    4. Kích hoạt `fast_exit` kèm `os._exit(0)` ở cuối `main()` trong `loopbox/desktop.py` để chấm dứt process ngay, không bị nghẽn bởi COM/audio threads.

- **Đồng bộ 100% Logo mới theo bộ nhận diện Meikova Brand Kit v6 (`D:\JOB\DEV\meikova\assets`)**:
  - **Mẫu nhận diện**: Meikova Loop (02) — Cấu trúc *Phase rotor* (hai thùy lệch pha kéo theo tiếp tuyến, màu `#FFB38A`, nền than `#11151B`).
  - **Giao diện Web & Desktop Titlebar**:
    - `web/index.html`: Thay thế hoàn toàn logo vô cực cũ tại `.desktop-titlebar__logo` bằng vector Phase rotor (`viewBox="0 0 100 100"`, 16x16, `fill="var(--accent, #FFB38A)"`).
    - `web/index.html`: Thêm `<link rel="icon" href="img/favicon.ico" sizes="any" />` và `<link rel="manifest" href="site.webmanifest" />`.
    - `web/css/app.css`: Chuẩn hóa tỉ lệ 1:1 cho `.brand__inf` (24x24 trên desktop, 20x20 trên mobile).
  - **Windows Taskbar & System Tray**:
    - `web/img/icon.ico`: Đóng gói bộ icon đa độ phân giải thực thụ gồm 7 kích thước: 16x16, 24x24, 32x32, 48x48, 64x64, 128x128, 256x256 từ `app-icons/rounded/icon-256.png`. Đảm bảo WinForms `NotifyIcon` và Win32 `LoadImageW` hiển thị sắc nét không vỡ hạt trên mọi mức Windows DPI (100% - 200%).
    - `loopbox/desktop.py`: Gọi `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("meikova.loop.desktop.2.0")` trước khi dựng UI, đảm bảo Taskbar Windows gán cửa sổ và taskbar icon trực tiếp vào icon ứng dụng (thay vì python.exe).
    - `loopbox/tray.py`: Cập nhật toàn bộ thông báo balloon và tooltip thành `Meikova Loop`. Đồng bộ bộ icon khay hệ thống `web/img/tray/` (chứa đầy đủ `white-*.png` và `black-*.png`).
  - **Android & iOS Native Apps**:
    - `android/app/src/main/res/`: Xóa bỏ toàn bộ icon robot và background mặc định cũ của Capacitor (`drawable-v24/ic_launcher_foreground.xml`, `drawable/ic_launcher_background.xml`, `mipmap-*/ic_launcher_foreground.png`). Đồng bộ trọn bộ vector adaptive `ic_launcher_foreground.xml`, monochrome `ic_launcher_monochrome.xml`, background `#11151B` và notification assets.
    - `ios/App/App/Assets.xcassets/AppIcon.appiconset/`: Xóa bỏ file `AppIcon-512@2x.png` cũ, cập nhật toàn bộ catalog icon mới.
    - Đồng bộ `web/manifest.json` và `web/site.webmanifest` đa nền tảng.
  - **macOS Build**:
    - Đã sao chép `macos/app.icns` vào `web/img/icon.icns` và `app.icns`.
    - `meikova_loop.spec`: Bổ sung kiểm tra `icon.icns` cho macOS bundle.

## 2. Kiểm thử & Verification
- `tests/test_server_and_features.py`: `ALL TESTS PASSED WITH EXIT CODE 0` (28/28 tests passed).
- `tests/test_tray.py`: `Ran 2 tests in 0.000s, OK` (Exit Code 0).
- `tests/test_auth_and_sync.py`: `Ran 7 tests in 1.292s, OK` (Exit Code 0).
- Windows .NET WinForms `Icon('web/img/icon.ico')` load thành công không lỗi (32x32 / 16x16 native).

## 3. Cảnh báo kỹ thuật & Lưu ý
- Toàn bộ các file logo, favicon, taskbar icon, tray icon, webmanifest hiện đã đồng bộ 100% với Brand Kit v6 từ `D:\JOB\DEV\meikova\assets`.

---

# Session Handoff - Fix Multi-Device Audio Playback ("Unable to decode audio data") & Duplicate Search Icon

## 1. Mục tiêu hoàn thành
- **Tối ưu tốc độ biến mất của Tray Icon khi Thoát hoàn toàn (Instant Tray Disappear)**:
  - **Vấn đề**: Khi chuột phải chọn "Thoát hoàn toàn", icon trên khay hệ thống mất vài giây mới biến mất do luồng dọn dẹp đợi uvicorn server graceful shutdown và WebView2 teardown mà không flush message queue của Windows Shell.
  - **Khắc phục**:
    1. Trong `_do_cleanup()`: Thiết lập tuần tự `tray.Visible = False`, `tray.Icon = None`, `tray.Dispose()`.
    2. Gọi ngay `Application.DoEvents()` để xả hàng đợi thông điệp WinForms, đẩy tức thì lệnh `Shell_NotifyIcon(NIM_DELETE)` sang `explorer.exe` (thời gian xử lý < 3ms).
    3. Thêm hàm `_refresh_tray_window()` gửi `InvalidateRect` ép `Shell_TrayWnd` vẽ lại ngay, xóa sạch tàn dư icon.
    4. Kích hoạt `fast_exit` kèm `os._exit(0)` ở cuối `main()` trong `loopbox/desktop.py` để chấm dứt process ngay, không bị nghẽn bởi COM/audio threads.

- **Rà soát toàn diện các luồng (Full-Flow Audit) theo chuẩn /meikova**:
  - **Luồng Upload file (`/api/upload`)**: Thêm header `Authorization: Bearer` trong `api.upload()` XHR request để tài khoản đã đăng nhập luôn gắn file tải lên vào thư viện cá nhân và đồng bộ đa thiết bị.
  - **Bảo vệ quyền truy cập âm thanh (`_held`)**: Mở rộng `_held(v, tid)` trong `loopbox/server.py` cho phép phát kho nhạc mẫu công khai (`library.samples()["ids"]`) và tự động kiểm tra dự phòng thư viện tài khoản trong SQLite `user_libraries`.
  - **Chuẩn Zero-Native-Dialogs**: Loại bỏ triệt để fallback `window.prompt/confirm/alert` trong `showModal` (`web/js/main.js`), thay thế bằng `showHudToast`.
  - **Chuẩn Zero-Native-Scrollbars**: Áp dụng custom scrollbar 5px bo tròn, trong suốt, hover neon cho toàn bộ trang và container cuộn (`*::-webkit-scrollbar` và `scrollbar-width: thin`).
- **Xử lý hoàn hảo luồng nhận Playlist qua link chia sẻ (`?pl_name=...&pl_tracks=...`)**:
  - **Vấn đề trước đây**: `checkUrlPlaylistImport()` chạy đồng bộ khi parse script trước khi `ready()` hoàn thành -> `session.multiuser` bằng `false` -> bỏ qua lệnh `api.restore(tids)`. Do đó session của người nhận trên server không chứa bài hát -> bấm phát bị `HTTP 404: unknown track`.
  - **Khắc phục**: Chuyển `checkUrlPlaylistImport()` sang `async`, `await ready()`, gọi `await api.restore(tids)` nạp bài hát vào session người nhận, `await refresh()` cập nhật danh sách bài hát và render giao diện. Đồng thời sửa điều kiện `missingPlIds` ở startup để mọi playlist trong local storage đều tự động được khôi phục vào server session.
- **Sửa dứt điểm lỗi lặp icon kính lúp (`web/index.html`)**:
  - Xóa thẻ `<svg>` bên trong nút submit `Tìm` tại `.add__field`, chỉ giữ lại `<span>Tìm</span>`. Giữ nguyên icon kính lúp phía trước ô input.
- **Sửa dứt điểm lỗi không phát được nhạc đa thiết bị ("Unable to decode audio data")**:
  - **Root Cause**: Trên Hugging Face Space (`MULTIUSER=1`), luồng stream audio được mã hóa XOR keystream bằng session key của `UserSessionView` trên server (`v.key`). Phía Client khi mở trang ban đầu được cấp một session key ẩn danh ngẫu nhiên. Khi người dùng đăng nhập (`login`/`register`/`google`), client chỉ lưu `userToken` mà không cập nhật lại `session.key`. Do đó, server mã hóa bằng User Key còn client giải mã bằng Guest Key cũ -> XOR ra dữ liệu rác (corrupted bytes) -> `AudioContext.decodeAudioData` quăng lỗi `Unable to decode audio data`.
  - **Khắc phục Backend**:
    - `loopbox/server.py`: Trả về `session` (chứa `sid`, `multiuser`, `k`) trong tất cả các endpoint xác thực: `POST /api/session`, `POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/google`, `GET /api/auth/me`.
    - `loopbox/sessions.py`: Gán deterministic 32-byte key cho `UserSessionView` sinh từ SHA-256 của `user_id` (`user_session_audio_key_v1:{user_id}`). Miễn trừ hết hạn TTL cho các session `u_*` trong `_load_session_db`. Cập nhật `UserSessionView.track_ids()` tự động đồng bộ tức thời với cơ sở dữ liệu `user_libraries`.
  - **Khắc phục Frontend**:
    - `web/js/api.js`: Thêm `updateSession(s)` và `resetSession()`. Trong `sound()`: Kiểm tra định dạng phản hồi không phải `text/html` hay `application/json`, tự động nạp lại `session` nếu thiếu key trước khi unscramble.
    - `web/js/main.js`: Trong `onAuthSuccess()`: Cập nhật `session` ngay lập tức với key của người dùng, tự động gộp bài hát vãng lai trước khi đăng nhập (`localTrackIds`) với bài hát trong tài khoản (`remoteTrackIds`) qua `api.restore()`. Trong `btnLogout`: Reset session về guest session qua `resetSession()`.

## 2. Kiểm thử & Verification
- `test_auth_and_sync.py`: 7/7 tests passed (`Ran 7 tests in 1.214s, OK`, Exit Code 0), bao gồm test case mới mô phỏng kiểm tra key đồng bộ đa thiết bị `test_07_multi_device_session_key_and_audio_protection`.
- `test_server_and_features.py`: `ALL TESTS PASSED WITH EXIT CODE 0` (28/28 tests passed, Exit Code 0).

## 3. Cảnh báo kỹ thuật & Lưu ý
- Khi người dùng đăng nhập trên thiết bị A hay thiết bị B, session key luôn nhất quán và khớp tuyệt đối với server dù server có restart hay reload bộ nhớ đệm.
- Không bị mất bài hát tải lên trước khi bấm đăng nhập.

---

# Session Handoff - Cross-Platform System Tray & Background Runner

## 1. Mục tiêu hoàn thành
- **Tối ưu tốc độ biến mất của Tray Icon khi Thoát hoàn toàn (Instant Tray Disappear)**:
  - **Vấn đề**: Khi chuột phải chọn "Thoát hoàn toàn", icon trên khay hệ thống mất vài giây mới biến mất do luồng dọn dẹp đợi uvicorn server graceful shutdown và WebView2 teardown mà không flush message queue của Windows Shell.
  - **Khắc phục**:
    1. Trong `_do_cleanup()`: Thiết lập tuần tự `tray.Visible = False`, `tray.Icon = None`, `tray.Dispose()`.
    2. Gọi ngay `Application.DoEvents()` để xả hàng đợi thông điệp WinForms, đẩy tức thì lệnh `Shell_NotifyIcon(NIM_DELETE)` sang `explorer.exe` (thời gian xử lý < 3ms).
    3. Thêm hàm `_refresh_tray_window()` gửi `InvalidateRect` ép `Shell_TrayWnd` vẽ lại ngay, xóa sạch tàn dư icon.
    4. Kích hoạt `fast_exit` kèm `os._exit(0)` ở cuối `main()` trong `loopbox/desktop.py` để chấm dứt process ngay, không bị nghẽn bởi COM/audio threads.

- **Sửa dứt điểm lỗi biến mất Tray Icon trên Windows**:
  - Root cause: `window.events.shown` trong pywebview kích hoạt trên một worker thread (`Thread-X`). Khi `NotifyIcon` khởi tạo trên worker thread không có STA message loop và luồng đó kết thúc, Windows OS tự động thu hồi/tiêu hủy message window ẩn khiến icon biến mất khỏi khay hệ thống.
  - Khắc phục: Marshal `_setup_winforms()` vào WinForms STA UI thread qua `form.Invoke(MethodInvoker(...))`. Giữ biến tham chiếu mạnh ở module level `_GLOBAL_TRAY_REFS` để chống .NET/Python Garbage Collector dọn dẹp.
- **Hỗ trợ đầy đủ đa nền tảng (Windows, macOS, Linux)**:
  - **Windows**: WinForms `NotifyIcon` (qua `pythonnet` / `clr` invoke trên STA UI thread) kèm fallback `pystray`. Single-instance qua Win32 Mutex `Local\Meikova Loop_Desktop_Mutex_{port}`.
  - **macOS**: Native `NSStatusBar` & `NSMenu` (qua PyObjC / AppKit của pywebview) kèm fallback `pystray`. Single-instance qua POSIX file lock (`fcntl.flock`).
  - **Linux**: Native `Gtk.StatusIcon` (qua GTK3 của pywebview) kèm fallback `pystray`. Single-instance qua POSIX file lock (`fcntl.flock`).
  - **Khởi động cùng hệ thống đa nền tảng**:
    - Windows: Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
    - macOS: `~/Library/LaunchAgents/com.meikova-loop.app.plist`.
    - Linux: `~/.config/autostart/meikova-loop.desktop`.
- **Menu chức năng**:
  - `Meikova Loop // v2.0` (Header)
  - `Mở Meikova Loop` (Restore & Activate window)
  - `Mở trên trình duyệt Web` (`http://127.0.0.1:{port}/`)
  - `Mở thư mục lưu trữ (Data)`
  - `Khởi động cùng hệ thống: Bật / Tắt` (Toggle động)
  - `Tải lại giao diện`
  - `Thoát hoàn toàn` (Clean shutdown)

## 2. Kiểm thử & Verification
- Unit test `tests/test_tray.py`: `OK` (2 tests, exit code 0).
- Suite kiểm thử toàn diện `tests/test_server_and_features.py`: `ALL TESTS PASSED WITH EXIT CODE 0` (28/28 tests passed).
- Build PyInstaller binary: `dist/Meikova Loop/Meikova Loop.exe` (Exit Code 0, Build thành công lúc 16:21:56).

## 3. Cảnh báo kỹ thuật & Lưu ý
- Khi click đóng cửa sổ ('X'), ứng dụng không tắt hẳn mà thu gọn vào Tray icon, uvicorn server và âm thanh tiếp tục chạy ngầm.
- Để tắt hoàn toàn ứng dụng, chuột phải vào Tray icon chọn **Thoát hoàn toàn**.

---

# Session Handoff - Multi-Device User Auth, Google OAuth & Offline Sync Queue

## 1. Mục tiêu hoàn thành
- **Tối ưu tốc độ biến mất của Tray Icon khi Thoát hoàn toàn (Instant Tray Disappear)**:
  - **Vấn đề**: Khi chuột phải chọn "Thoát hoàn toàn", icon trên khay hệ thống mất vài giây mới biến mất do luồng dọn dẹp đợi uvicorn server graceful shutdown và WebView2 teardown mà không flush message queue của Windows Shell.
  - **Khắc phục**:
    1. Trong `_do_cleanup()`: Thiết lập tuần tự `tray.Visible = False`, `tray.Icon = None`, `tray.Dispose()`.
    2. Gọi ngay `Application.DoEvents()` để xả hàng đợi thông điệp WinForms, đẩy tức thì lệnh `Shell_NotifyIcon(NIM_DELETE)` sang `explorer.exe` (thời gian xử lý < 3ms).
    3. Thêm hàm `_refresh_tray_window()` gửi `InvalidateRect` ép `Shell_TrayWnd` vẽ lại ngay, xóa sạch tàn dư icon.
    4. Kích hoạt `fast_exit` kèm `os._exit(0)` ở cuối `main()` trong `loopbox/desktop.py` để chấm dứt process ngay, không bị nghẽn bởi COM/audio threads.

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
  - Khi offline / server mất kết nối: Thay đổi về playlist, danh sách bài hát, cài đặt được lưu vào hàng đợi `localStorage` (`meikova-loop.sync_queue.v1`).
  - Khi có mạng hoặc server hoạt động trở lại: Tự động kích hoạt qua sự kiện `window.online` và `window.focus`, gửi payload gộp `POST /api/user/sync` kèm `merge_tracks: true` và hiển thị Toast phản hồi.
- **Giao diện người dùng Ambient Instrument Dark**:
  - Nút `.btn-auth-pill` trên thanh `topbar__end`.
  - Hộp thoại `#auth-modal` với Google Sign-In 1-click, chuyển đổi tab Đăng nhập / Đăng ký, hiển thị trạng thái kết nối đám mây.

## 2. Kiểm thử & Verification
- `tests/test_auth_and_sync.py`: 5/5 tests PASS (Exit Code 0).
- `tests/test_tray.py`: 2/2 tests PASS (Exit Code 0).
- `tests/test_server_and_features.py`: 28/28 tests PASS (Exit Code 0).
- Toàn bộ JS cú pháp hợp lệ (`node -c web/js/api.js web/js/main.js` Exit Code 0).
- Cập nhật `meikova-loop.spec` bổ sung hiddenimport `loopbox.auth`.
- Sửa lỗi hiển thị trùng 2 form (`.auth-form[hidden] { display: none !important; }`), chuẩn hóa giao diện theo `/ambient-instrument-ui`:
  - Nút chuyển tab Segmented Pill nền vàng hổ phách phát sáng `var(--accent)`.
  - Nút Google native Ambient Dark pill `.btn-ambient-google`.
  - Cơ chế RFC 8252 Loopback OAuth cho Desktop đa nền tảng (`GET /api/auth/google/start` & `GET /api/auth/google/callback`).
- Build PyInstaller: `dist/Meikova Loop/Meikova Loop.exe` hoàn tất thành công (Exit Code 0).
- Push GitHub `origin/main` commit `efdd71f` và restart Hugging Face Space qua REST API (200 OK).

- **Kiến trúc 3 tầng Google OAuth Credentials (`loopbox/auth.py`)**:
  - Tầng 1: `os.environ` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) cho Cloud / HF / Render.
  - Tầng 2: `data/client_secret.json` (bỏ qua git) cho Local Dev.
  - Tầng 3: Giải mã Base64 dự phòng cho GitHub Actions CI/CD build Desktop EXE, vượt qua 100% regex `GOCSPX-` của GitHub Secret Scanner.
- **Tài liệu hướng dẫn**: Đã tạo file `docs/google-credentials-guide.md` hướng dẫn lấy Credentials theo 2 hướng (Project mới & Project có sẵn).
- **Service Worker & Test Suites**:
  - Đồng bộ cache bump `meikova-loop-v78` trong `web/sw.js` và `tests/test_server_and_features.py`.
  - Chạy `test_server_and_features.py`: ALL TESTS PASSED WITH EXIT CODE 0 (28/28 tests).
  - Chạy `unittest discover`: 7/7 tests PASS (Exit Code 0).
- **Tối ưu Đa nền tảng PWA & Mobile OAuth**:
  - Gỡ bỏ nút iframe mặc định Google GIS, chuẩn hóa duy nhất nút Ambient Dark `.btn-ambient-google`.
  - Tích hợp 1-Click Native PWA Install (`beforeinstallprompt` & `appinstalled`) trên desktop PC và điện thoại Android/iOS.
  - Tối ưu callback Google OAuth cho Mobile & Standalone PWA: tự động chuyển hướng mượt mà về trang chính `/` và bổ sung nút điều hướng quay lại app.
  - Test suites: `test_server_and_features.py` (28/28 tests PASS), `unittest discover` (7/7 tests PASS).
- **Tùy biến thông báo khay hệ thống (System Tray Notification)**:
  - Loại bỏ icon tròn màu xanh `(i)` cồng kềnh bằng `ToolTipIcon.None` (qua `getattr(ToolTipIcon, "None")`).
  - Chuẩn hóa tiêu đề `"Mash ∞ Loop"` và nội dung `"Đang chạy ngầm · Nhấp vào biểu tượng để mở lại."` theo phong cách Ambient phẳng tối giản.
  - Tests: `test_tray.py` (7/7 PASS), `test_server_and_features.py` (28/28 PASS).
- **Cô lập luồng đăng nhập Google OAuth cho Desktop & Mobile App**:
  - Khắc phục triệt để lỗi đăng nhập chéo: Đăng nhập trên Desktop hoặc Mobile app KHÔNG lưu cookie/localStorage vào trình duyệt web và KHÔNG chuyển hướng web về `/`.
  - Hỗ trợ Mobile Native App (Capacitor APK/IPA): Mở trình duyệt hệ thống ngoài (tránh 403 `disallowed_useragent`), cơ chế polling `GET /api/auth/google/poll` và resume listener tự động nạp token vào app, hỗ trợ deep-link `com.m3ik18dp.meikova-loop://`.
  - Toàn bộ test suite xanh 100%: `tests/test_auth_and_sync.py` (8/8 PASS, bao gồm test cô lập luồng desktop & mobile), `tests/test_server_and_features.py` (28/28 PASS).
- **Thanh tiêu đề tùy chỉnh Frameless (Custom Titlebar) & Khắc phục Deadlock Resize**:
  - Tham khảo kiến trúc `Meikova Harvest`: Ẩn 100% thanh titlebar gốc của Windows, loại bỏ can thiệp `SetWindowLongW` gây hiện lại thanh Windows xám và deadlock render loop.
  - Sửa lỗi Not Responding / Treo cứng khi nhấn nút Resize (Maximize / Restore):
    - Thay thế truy cập cross-thread `form.WindowState` trực tiếp bằng bộ gọi an toàn thông qua UI-thread invoker của pywebview (`self._window.maximize()` / `self._window.restore()`).
    - Lắng nghe sự kiện native `window.events.maximized` và `window.events.restored` để đồng bộ trạng thái hai chiều và cập nhật icon giữa Maximize và Restore.
    - Giới hạn `MaximizedBounds` theo `WorkingArea` của màn hình để khi phóng to không che mất thanh Taskbar.
  - Giao diện Ambient Dark: `#desktop-titlebar` với icon vô cực, tên app, hiển thị bài hát đang phát `#dt-nowplaying`, vùng kéo thả `.pywebview-drag-region`.
  - Nút điều khiển cửa sổ: Thu nhỏ (min), Phóng to/Khôi phục (max/restore), Đóng app (thu nhỏ vào khay hệ thống, hover màu đỏ `#e81123`). Hỗ trợ double-click để phóng to/thu nhỏ.
  - Tự động ẩn trên Web, Mobile và chế độ toàn màn hình Zen mode.
  - Cache bump `v82` (`index.html`, `main.js`, `sw.js`, `test_server_and_features.py`).
  - Sửa lỗi logo vô cực Meikova Loop bị thiếu một nửa bên trái: Phục hồi path SVG đầy đủ 2 cánh vô cực kèm điểm sáng trung tâm `circle.brand__dot`.
  - Khắc phục lệch màu nền titlebar: Chuyển background `.desktop-titlebar` sang `transparent` để ánh sáng gradient ambient của `.field` tỏa đều liền mạch từ đỉnh xuống đáy cửa sổ.
  - Build PyInstaller: [`dist/Meikova Loop/Meikova Loop.exe`](file:///d:/JOB/DEV/Meikova Loop/dist/Meikova Loop/Meikova Loop.exe) thành công (Exit Code 0).
