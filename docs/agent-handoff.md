# PROJECT SESSION HANDOFF LOG

## Project Status
- Path: D:\JOB\DEV\MashLoop\
- Setup Mode: Upgrade, Desktop Native Shell, ONNX Inference & Mobile Capacitor Shell
- Initialized with Antigravity Titan Standards.

## Last Updated
- Timestamp: 2026-10-20 10:07:00
- Exit Code: 0 (All 25 test suites passed: tests/test_server_and_features.py)
- Platforms Built & Supported: 5 platforms (Windows Desktop, macOS Desktop, Linux Desktop, Android APK, iOS IPA) across GitHub Actions CI/CD (`.github/workflows/build-release.yml`), Desktop Native Shell (`loopbox/desktop.py`, `mashloop.spec`), GitHub (`origin/main`), HF Space (`m3ik18dp/MashLoop`).

## Cải tiến & Khắc phục Mới Nhất
- **Khắc phục lỗi CI/CD Build Linux: thiếu `girepository-2.0` khi build PyGObject**:
  - **Nguyên nhân**: Runner `ubuntu-latest` chạy Ubuntu 24.04 (noble). PyGObject 3.50+ yêu cầu thư viện GObject-Introspection bản 2.0 (`girepository-2.0`). Trước đây workflow chỉ cài `libgirepository1.0-dev`, không có `libgirepository-2.0-dev` và `libcairo2-dev`, khiến `meson` báo lỗi `Dependency 'girepository-2.0' is required but not found`.
  - **Khắc phục**:
    1. Cập nhật `.github/workflows/build-release.yml`: bổ sung `libgirepository-2.0-dev`, `libgirepository1.0-dev`, `libcairo2-dev`, `gobject-introspection`, `pkg-config` vào bước `Install System Dependencies`.
    2. Cài thêm `wheel setuptools` trước khi build `PyGObject` qua pip.
    3. Kiểm tra test suite đạt Exit Code 0.

- **Mở rộng hỗ trợ Đa Nền tảng Toàn diện (Linux & macOS Desktop) & Universal Media Controls**:
  - **Mục tiêu**: Xây dựng ứng dụng native desktop cho cả Linux (`.tar.gz`) và macOS (`.app` / `.zip`) song song với Windows (`.exe` / `.zip`), Android (`.apk`), iOS (`.ipa`). Đảm bảo hệ thống điều khiển phát nhạc tích hợp sâu với OS:
    1. **Windows**: System Media Transport Controls (SMTC) overlay & phím Media phần cứng.
    2. **iOS (iPhone/iPad)**: Lock Screen Now Playing widget, Dynamic Island, Control Center, phím tai nghe AirPods.
    3. **macOS**: Now Playing widget, Control Center, Touch Bar, phím F7/F8/F9.
    4. **Android**: Lock Screen Media Notification, Quick Settings media tile.
    5. **Linux**: MPRIS2 D-Bus interface tích hợp với panel môi trường GNOME / KDE / XFCE.
  - **Thay đổi chi tiết**:
    1. **`loopbox/desktop.py`**:
       - Bọc bảo vệ `ctypes.wintypes` trong `if sys.platform == "win32":` để tránh crash ImportError/AttributeError trên macOS và Linux.
       - Cung cấp class `WindowsVolume` fallback tương thích đa nền tảng.
    2. **`mashloop.spec`**:
       - Tự động nhận diện nền tảng `sys.platform`:
         - Windows: hiddenimports `clr`, `webview.platforms.winforms`.
         - macOS (`darwin`): hiddenimports `webview.platforms.cocoa`, `objc`; cấu hình `BUNDLE` tạo `MashLoop.app` với bundle identifier `com.mashloop.app`.
         - Linux: hiddenimports `webview.platforms.gtk`, `gi`.
    3. **`.github/workflows/build-release.yml`**:
       - Thêm job `build-linux` (runner `ubuntu-latest`, cài `libwebkit2gtk-4.1-dev`, `PyGObject`, nén `MashLoop-Linux.tar.gz`).
       - Thêm job `build-macos` (runner `macos-14`, cài `pyobjc-framework-WebKit`, nén `MashLoop-macOS.zip` chứa `MashLoop.app`).
       - Tự động phát hành đầy đủ 5 nền tảng lên GitHub Releases (`MashLoop-Windows.zip`, `MashLoop-macOS.zip`, `MashLoop-Linux.tar.gz`, `MashLoop.apk`, `MashLoop.ipa`).
    4. **`loopbox/server.py`**:
       - Mở rộng `/api/download/{target}` hỗ trợ `macos` (`MashLoop-macOS.zip`) và `linux` (`MashLoop-Linux.tar.gz`), tự động chuyển hướng 307 tới GitHub Releases.
    5. **`ios/App/App/AppDelegate.swift`**:
       - Import `AVFoundation` và cấu hình `AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [.mixWithOthers, .allowAirPlay, .allowBluetooth])` để giữ background audio và hiển thị widget Lock Screen / Dynamic Island.
    6. **`web/index.html` & `web/css/app.css`**:
       - Cập nhật modal tải ứng dụng với đủ 5 thẻ nền tảng (Windows `.EXE`, macOS `.APP`, Linux `.TAR.GZ`, Android `.APK`, iOS `.IPA`) theo chuẩn Design System (Zero-Icon, 100% Inline SVG, OKLCH, căn thẳng hàng baseline).
       - Bổ sung thẻ hướng dẫn Desktop (Windows SMTC, macOS Now Playing, Linux MPRIS2).
    7. **Kiểm thử tự động (`tests/test_server_and_features.py`)**:
       - Bổ sung suite `test_cross_platform_releases_and_media_controls` kiểm tra toàn bộ 5 route download, spec, workflow, AppDelegate và HTML.
       - Đạt 25/25 tests Pass với Exit Code 0.

- **Khắc phục lỗi các nút điều khiển Media trên Windows (SMTC overlay của Edge) không thao tác được**:
  - **Nguyên nhân**:
    1. **Nút Next (`>>|`)**: `mediasession.js` gọi `player.requestNextSong()` chỉ bật cờ nội bộ `urgent = true` chờ bộ lập lịch tới điểm ra của bài (có thể mất vài phút hoặc không có tác dụng ở chế độ Single), không chuyển bài ngay khiến người dùng thấy bấm không phản hồi.
    2. **Nút Previous (`|<<`)**: `mediasession.js` gọi `player.requestJump()` chỉ bật cờ `jumpNow = true` để tìm điểm nhảy trong bài thay vì tua lại đầu bài hoặc lùi về bài trước trong lịch sử phát.
    3. **Nút Play/Pause (`||` / `▶`)**: Khi tạm dừng, `engine.stopAnchor()` trước đây thiết lập `setTimeout` 3 phút mới dừng thẻ `<audio>` chạy ngầm `silence.mp3`. Do thẻ audio vẫn `paused == false`, Edge báo cho Windows SMTC rằng media vẫn đang chạy, dẫn đến xung đột trạng thái giữa `mediaSession.playbackState = "paused"` và `HTMLMediaElement.paused = false` (Windows SMTC bị kẹt ở icon Pause `||`, không hiển thị icon Play `▶` để bấm tiếp tục). Ngoài ra thiếu sự kiện `play` trên thẻ audio để bắt lệnh phát từ phím phần cứng / SMTC.
    4. **Lỗi W3C Media Session Spec**: `updatePositionState()` truyền `playbackRate = 0` khi dừng, vi phạm chuẩn W3C khiến Chromium ném `TypeError: The playback rate must not be zero`.
    5. **Bug gọi hàm không tồn tại**: Trong `player.js` dòng 567 gọi `this.seekTo(0)` (hàm đúng là `this.seek(0)`).
  - **Khắc phục**:
    1. `safeSetHandler("nexttrack")`: chuyển sang gọi trực tiếp `await player.skipToNext()` (hoặc `forceTransition()`), thực hiện DJ crossfade mượt mà sang bài kế tiếp ngay lập tức khi bấm.
    2. `safeSetHandler("previoustrack")`: nếu bài đã phát qua 4 ô nhịp (`beat > 16`) thì tua lại đầu bài (`player.seek(0)`); nếu ở đầu bài thì lấy bài trước từ `player.history` (`player.start(prevId)`), đúng chuẩn trải nghiệm Spotify / Apple Music / Windows Media Player.
    3. `web/js/engine.js`: cập nhật `stopAnchor()` ngắt ngay thẻ `<audio>` để Chromium lập tức chuyển trạng thái sang Paused và đổi icon SMTC sang `▶`. Bổ sung listener `a.addEventListener("play")` và callback `_onExternalPlay` trong `player.js` để đồng bộ 2 chiều khi Windows ra lệnh Play.
    4. `updatePositionState()`: đảm bảo `playbackRate` luôn $> 0$ (kẹp trong khoảng `0.25 .. 4.0`), loại bỏ triệt để TypeError.
    5. Sửa `this.seekTo(0)` thành `this.seek(0)` trong `player.js`.
    6. Bổ sung bài kiểm thử tự động `test_mediasession_windows_smtc_controls` trong `tests/test_server_and_features.py` (24/24 tests Pass).
    7. Đồng bộ toàn bộ code sang `dist/MashLoop/_internal/web/`.

- **Khắc phục lỗi chuyển động vô cực chỉ chạy nửa hình trên nút Play của Deck**:
  - **Nguyên nhân**: Trong commit `e1f5d61`, khi canh chỉnh format HTML, thẻ `<path>` của SVG `.i-load` trên nút `#btn-play` vô tình bị xoá mất nửa vòng lemniscate bên trái (` C 18 4, 6 4, 6 12 C 6 20, 18 20, 24 12 Z`), chỉ còn vòng bên phải (`d="M24 12 C 30 4, 42 4, 42 12 C 42 20, 30 20, 24 12 Z"`). Khi animation `@keyframes trace` chạy với `stroke-dashoffset: 0 -> -120` và `stroke-dasharray: 26 94`, nét vẽ chỉ chạy trên vòng bên phải rồi biến mất ở nửa chu kỳ còn lại vì không còn đường dẫn SVG.
  - **Khắc phục**:
    1. Khôi phục hoàn chỉnh đường cong lemniscate 2 cánh trong `web/index.html`: `d="M24 12 C 30 4, 42 4, 42 12 C 42 20, 30 20, 24 12 C 18 4, 6 4, 6 12 C 6 20, 18 20, 24 12 Z"`.
    2. Bổ sung thuộc tính chuẩn SVG `pathLength="120"` trên `<path>` để đồng bộ tuyệt đối 1:1 với `stroke-dasharray: 26 94` (26 + 94 = 120) và `@keyframes trace { to { stroke-dashoffset: -120; } }`, chuyển động mượt mà không khựng không giật.
    3. Cố định `height: 15px` tại `.deck__play[data-state="load"] .i-load` trong `web/css/app.css` khớp tỷ lệ 2:1 của `viewBox="0 0 48 24"`.
    4. Bổ sung bài kiểm thử tự động `test_deck_infinity_loading_path` trong `tests/test_server_and_features.py` (23/23 tests Pass).
    5. Đồng bộ sang `dist/MashLoop/_internal/web/`.

- **Nâng Cấp & Chuẩn Hóa Skill `ambient-instrument-ui` (Zero-Icon, 100% Inline SVG & Less Text)**:
  - **Mục tiêu**: Loại bỏ triệt để việc dùng icon mơ hồ / icon font / emoji. Chuẩn hóa 100% Inline Vector `<svg>` căn thẳng hàng tuyệt đối với chữ, giảm thiểu tối đa văn bản ("Less Text, More Signal"), thay thế chữ bằng SVG tự giải thích và micro-copy ngắn gọn (tối đa 1–2 từ).
  - **Thay đổi chính**:
    1. **Zero-Icon Mandate**: Cấm icon fonts và emoji. Mọi glyph đều là Inline `<svg viewBox="0 0 24 24" stroke="currentColor">` kế thừa màu phát quang OKLCH (`--accent`).
    2. **Pixel-Perfect Optical Baseline Alignment**: Loại bỏ lỗi nhảy 1-2px baseline giữa SVG và chữ bằng `.btn-pill { display: inline-flex; align-items: center; vertical-align: middle; gap: 6px; }`, `.btn-pill svg { display: block; flex-shrink: 0; }`, `.btn-pill span { line-height: 1; transform: translateY(-0.5px); }`, và text-inline `vertical-align: -0.125em`.
    3. **Tối Giản Văn Bản (Visual Telemetry over Text)**: Bổ sung bảng đối chiếu thay thế các câu dài thành SVG trực quan + nhãn micro-copy 1 từ (`Phát`, `Nhảy`, `Tiếp`, `Lặp`, `Zen`, `Tải`, `Chọn`) kèm đầy đủ `aria-label` / `title` cho Accessibility.
    4. **Tài liệu tham khảo mới**: Bổ sung [`references/svg-craft-and-minimal-text.md`](file:///d:/JOB/DEV/MashLoop/.agents/skills/ambient-instrument-ui/references/svg-craft-and-minimal-text.md) và cập nhật [`examples/tokens.css`](file:///d:/JOB/DEV/MashLoop/.agents/skills/ambient-instrument-ui/examples/tokens.css) với các lớp tiện ích `.btn-pill`, `.chip`, `.btn-icon-pure`.

- **CI/CD GitHub Actions & Tự động Build Apps (Android APK, iOS IPA, Desktop EXE)**:
  - **Khảo sát**: Space (Hugging Face) chạy Linux Docker container, không có macOS để chạy Xcode build IPA cho iOS và không phù hợp phần cứng để build Android. GitHub Actions là giải pháp chuẩn nhất.
  - **Triển khai CI/CD Workflow (`.github/workflows/build-release.yml`)**:
    1. **Android APK**: Runner `ubuntu-latest`, setup Java 21 & Android SDK, `npx cap sync android`, chạy `./gradlew assembleDebug`, xuất file `MashLoop.apk`.
    2. **iOS IPA**: Runner `macos-14`, setup Node & CocoaPods, `npx cap sync ios`, chạy `xcodebuild archive` và đóng gói unsigned Payload `MashLoop.ipa` (sẵn sàng cho AltStore / Sideloadly / TestFlight).
    3. **Windows Desktop**: Runner `windows-latest`, setup Python 3.11, build PyInstaller onedir và nén thành `MashLoop-Windows.zip`.
    4. **GitHub Releases Automation**: Tự động phát hành và upload toàn bộ artifact khi tạo Release tag `v*` hoặc trigger thủ công `workflow_dispatch`.
  - **Backend Download Endpoints (`loopbox/server.py`)**:
    - Bổ sung `@app.api_route("/api/download/{target}", methods=["GET", "HEAD"])`.
    - Phục vụ trực tiếp file local nếu có (`MashLoop-Windows.zip`, `MashLoop.apk`, `MashLoop.ipa`).
    - Tự động 307 Redirect tới link GitHub Release mới nhất `https://github.com/m3iK18dp/mashloop/releases/latest/download/...` khi chạy trên Space hoặc cloud.
    - Hỗ trợ phương thức `HEAD` trả headers nhanh không tốn tài nguyên tải file dung lượng lớn.
  - **Mở rộng Width Modal & Giao diện Tải Ứng Dụng (`web/index.html` & `web/css/app.css`)**:
    - Tăng chiều rộng `.mobile-modal` và `.shortcuts-modal` từ `580px` lên `min(720px, calc(100vw - 28px)) !important;`.
    - Tách hộp URL máy chủ `.mobile-modal__sub-box` với Tag nền tảng (`Hugging Face Space`, `Tailscale Mesh`, `Local Host`), font monospace chống ngắt dòng và nút "Sao chép" một chạm.
    - Bổ sung cụm thẻ tải trực tiếp `.mobile-downloads`: nút tải **Android APK**, **Windows Desktop**, và **iOS IPA** kèm badge định dạng rõ ràng.
    - Cố định lề cột phím tắt `.shortcut-row dt` (min-width `90px`) và `.shortcut-row dd` (white-space `nowrap`), giải quyết triệt để lỗi rớt dòng ở phím `1 / 2 / 3` ("Chế độ Chuỗi / Đơn / Tự do").
    - Nâng cấp Cache phiên bản lên `mashloop-v76`.

- **Khắc phục lỗi Visualizer Crash (`ReferenceError: two is not defined`) & Báo lỗi Script sai khi mạng ngắt quãng**:
  - **Nguyên nhân**: Khi tối ưu swap animation trong `web/js/viz.js`, dòng khai báo `const two = !!(second || placeholder);` bị vô tình ghi đè, khiến vòng lặp `_update` ném `ReferenceError: two is not defined` mỗi frame làm visualizer tối đen. Đồng thời `web/js/main.js` bắt nhầm `TypeError: Failed to fetch` (vốn là lỗi mạng khi server restart) thành `Lỗi script: Failed to fetch`.
  - **Khắc phục**: Khôi phục biến `two` trong `viz.js`; xử lý lỗi `Failed to fetch` / `NetworkError` thành trạng thái "Đang kết nối lại server…", chỉ báo "Lỗi script" cho `ReferenceError` thực tế.

- **Nút "Chuyển ngay lập tức" (Skip / Immediate Transition) & Khắc phục lỗi bấm không phản hồi**:
  - **Nguyên nhân**: Nút `#btn-next` trước đây bị vô hiệu hóa khi không ở chế độ "chain" (`$("#btn-next").disabled = !player.cur || player.settings.mode !== "chain"`). Trong `web/js/player.js`, hàm `forceTransition` gọi hàm không tồn tại `this.pick(candidates[0])` thay vì `this.planTransition(candidates[0])`. Ngoài ra nếu bài đích chưa tải hoặc chưa có đường nối phân tích, người dùng không nhận được bất kỳ phản hồi nào.
  - **Khắc phục**:
    1. Sửa hàm `this.pick(...)` thành `this.planTransition(...)`.
    2. Thêm phương thức `player.skipToNext()`: tự động kích hoạt chuyển bài tức thì (immediate DJ crossfade 2.5s) sang bài kế tiếp trong playlist hoặc thư viện nếu chưa có plan, hoặc tua nhanh transition plan đang chờ mà không phải đợi tới điểm ra xa.
    3. Cho phép nút `#btn-next` hoạt động ở mọi chế độ (chỉ cần có bài đang phát).
    4. Thêm hiệu ứng xúc giác (tactile pulse) khi bấm và thông báo HUD Toast: "Đang chuyển sang bài tiếp theo (N)...".

- **Âm lượng Overdrive 150% & Dải màu đỏ đậm bầm (100% → 150%)**:
  - **Bối cảnh**: Người dùng yêu cầu cho phép chỉnh âm thanh vượt ngưỡng 100% lên tới 150%, đoạn từ 100% đến 150% chuyển mượt từ màu chủ đạo sang màu đỏ đậm bầm (`oklch(0.48 0.25 24)` / deep crimson).
  - **Triển khai**:
    1. Thuộc tính thanh trượt `#s-vol`: `min="0" max="1.5" step="0.01"`.
    2. Trong `web/js/main.js`: `setAppVolume(val)` mở rộng từ 0.0 đến 1.5. Cập nhật nhãn `#v-vol` hiển thị tới `150%`.
    3. Hàm `syncVolumeRange(input)` tính toán gradient dải màu động `--vol-track`: đoạn 0% - 100% dùng màu chủ đạo `var(--accent)`, đoạn 100% - 150% nội suy mượt sang màu đỏ đậm bầm.
    4. Thẻ số `#v-vol` chuyển sang màu đỏ bầm và in đậm khi vượt 100%.
    5. Âm lượng hệ thống pywebview được giới hạn trần 1.0 trong khi Web Audio `Engine` xử lý phần gain boost qua compressor/limiter chống vỡ tiếng.
    6. Phím tắt `[` và `]` tăng/giảm bước 0.05 lên tới 150% kèm HUD Toast.

- **Bảng phím tắt & Khắc phục phím K (Đổi kho / Đổi Playlist)**:
  - **Bối cảnh**: Phím `K` trước đây gắn với `switchKho()` nhưng chỉ hoạt động khi dùng kho nhạc mẫu (`kho.cur`), nếu người dùng dùng bài tự upload hoặc playlist thì bấm `K` không phản hồi gì.
  - **Triển khai**:
    1. Nâng cấp `switchKho()`: Tự động tuần hoàn danh sách Playlist (`all` -> `playlist 1` -> `playlist 2` -> `all`) nếu có playlist, hoặc tuần hoàn kho mẫu nếu có nhiều kho, hoặc thông báo nếu chỉ có 1 kho duy nhất.
    2. Bổ sung phím tắt `1`, `2`, `3` đổi nhanh chế độ Chuỗi / Đơn / Tự do.
    3. Bổ sung phím `Escape` đóng nhanh các modal và thoát Zen mode.
    4. Cập nhật đầy đủ bảng phím tắt trong modal `Shortcuts Modal`.
    5. Thêm hệ thống `showHudToast` hiển thị thông báo góc nhìn nổi (ambient HUD toast) cho mọi phím tắt.

- **Mở rộng bảng màu theo Mood lên 14 Themes phong phú**:
  - Bổ sung 8 theme mới với bảng màu OKLCH cân chỉnh tỉ mỉ: `synthwave`, `emerald` (Rừng ngọc), `ocean` (Biển sâu), `magma` (Nham thạch), `solar` (Bão mặt trời), `arctic` (Băng tuyết), `midnight` (Đêm vô tận), `tokyo` (Tokyo đêm).
  - Thêm thẻ swatch tương ứng trong tab Tinh chỉnh và hỗ trợ xem trước màu (preview swatch).

- **Nâng cấp Animation chuyển tiếp mượt mà & đa dạng**:
  - Hỗ trợ animation chuyển đổi kích thước 2 vòng vô cực (`swap progress`) cho toàn bộ các kiểu mix (`fade`, `cut`, `drop`, `echo`, `wash`, `riser`, `flanger`, `tape`, `sweeper`), không chỉ riêng kiểu `blend`.
  - Hiệu ứng thị giác đa dạng tại điểm giao nhau `_drawCross`: sóng xung kích kép (drop/cut), vòng xoáy hạt năng lượng (riser/sweeper), sóng phản hồi đồng tâm (echo/wash), hào quang sương khói (fade/blend).
  - Nâng cấp `_drawRipples` thành sóng lan tỏa kép hai lớp.
  - Nâng cấp Cache phiên bản `mashloop-v75`.
- **Tính năng thanh trượt "Chuyển bài muộn nhất sau" (Dwell Max) động theo giới hạn nền tảng Server (Dynamic Dwell Duration Limits)**:
  - **Bối cảnh & Yêu cầu**:
    1. Mỗi nền tảng có giới hạn độ dài video khác nhau: Desktop / Local app cho phép xử lý video dài tới 60 phút (`3600s`), trong khi HF Space / Multiuser giới hạn 15 phút (`900s`).
    2. Thanh trượt `#s-dmax` ("Chuyển bài muộn nhất sau") trước đây bị fix cứng `max="900"` trong HTML, khiến người dùng Desktop không thể kéo lên trên 15 phút cho các mixtape / DJ set dài.
  - **Triển khai**:
    1. **Backend Platform-Aware (`loopbox/config.py`)**: `MAX_DURATION_S = _env_int("MASHLOOP_MAX_DURATION_S", 15 * 60 if MULTIUSER else 60 * 60)`. Tự động nhận diện 15 phút trên Space/Multiuser và 60 phút trên Desktop/Local.
    2. **Truyền `max_duration_s` qua các Endpoint Backend**: Bổ sung `max_duration_s` vào `@app.post("/api/session")` (trong `limits`), `@app.get("/api/tracks")`, và `@app.get("/api/settings")` trong `loopbox/server.py`.
    3. **Tự động điều chỉnh Slider Frontend (`web/js/main.js`)**:
       - Hàm `updateDurationLimits(maxSeconds)` cập nhật thuộc tính `.max` và `.step` của `#s-dmax` và `#s-dmin` dựa theo thông số trả về từ backend server.
       - Với desktop (3600s): `#s-dmax` tự động mở rộng trần lên 60 phút (step 30s), `#s-dmin` mở rộng trần lên 30 phút.
       - Tự động gọi khi nhận dữ liệu từ `/api/settings`, `/api/session`, và trong chu kỳ `refresh()` của `/api/tracks`.
    4. **Nâng cấp Cache**: `mashloop-v74` trong `web/sw.js` và `?v=74` trong `web/index.html`. Đồng bộ sang `dist/MashLoop/_internal/web/`.
    5. **Kiểm thử tự động**: Viết test suite `test_dynamic_dwell_and_server_duration_limits()` trong `tests/test_server_and_features.py` (Toàn bộ 20 test suites passed, Exit Code 0).

- **Khắc phục lỗi thanh trượt "Kích thước vòng vô cực" làm đổi màu thay vì đổi kích thước (Viz Scaling & Glow Decoupling Fix)**:
  - **Nguyên nhân gốc rễ**:
    1. **Kích thước bị triệt tiêu khi đang kéo (Scale Cancellation)**: Trong `web/js/viz.js`, hàm `setScale(s)` cập nhật `this.scale = s` và `this.layerR = this.baseR`. Tuy nhiên các vòng tròn `ring.r` đang phát được nội suy chậm bằng hàm exponential decay (`ring.r += (tg.r - ring.r) * k`). Trong `_drawRing`, hệ số tỉ lệ `s = ring.r / L.RL`. Khi `L.RL` lập tức mang giá trị mới trong khi `ring.r` còn giữ giá trị cũ, `s` đã tỉ lệ nghịch kéo thu nhỏ canvas texture về đúng kích thước cũ, làm vòng tròn không thay đổi kích thước tức thì khi người dùng đang kéo thanh trượt. Ngoài ra, hình vẽ `_idleGeom()` (2 vòng vô cực lúc chờ) hoàn toàn không nhân hệ số `this.scale`.
    2. **Đổi màu do hàm setGlow chạy thừa mứa**: Mỗi lần thanh trượt `#s-viz-scale` phát sinh sự kiện `input`, hàm `applySettings()` được kích hoạt và gọi `theme.setGlow(ui.glow)`. Trong `web/js/theme.js`, hàm `setGlow` không hề kiểm tra xem giá trị `userGlow` có thay đổi hay không mà luôn thực hiện `version++; cache.clear(); reapply()`. Điều này khiến toàn bộ cache màu (`beatColors`, `songColor`) bị xóa sạch, kích hoạt vẽ lại màu và re-render CSS variables `--acc-*`, tạo cảm giác "chỉnh kích thước nhưng lại đi chỉnh màu".
    3. `applySettings()` còn gọi `viz.invalidate()` không cần thiết mỗi lần bất kỳ thanh trượt nào di chuyển.
  - **Khắc phục**:
    1. **Thêm guard check trong `setGlow`**: `if (Math.abs(userGlow - next) < 0.001) return;` trong `web/js/theme.js`. Ngăn chặn hoàn toàn việc xóa cache màu và reapply style khi độ sáng neon không đổi.
    2. **Cập nhật kích thước tức thời trong `setScale`**: Khi `scale` thay đổi, lập tức nhân tỉ lệ `ratio = s / oldScale` vào `ring.r` và `ring.target.r` của tất cả các vòng tròn đang có trên sân khấu, giúp vòng to/nhỏ ngay lập tức dưới ngón tay/chuột người dùng mà không bị trễ hay lag.
    3. **Hỗ trợ phóng to/thu nhỏ 2 vòng lúc chờ (`_idleGeom`)**: Nhân `sc = this.scale || 1.0` vào bán kính `a` trong `_idleGeom()` và thêm `scale` vào cache key của `_idleLayer`.
    4. **Cô lập sự kiện `input` của `#s-viz-scale` và `#s-ui-scale`**: Gọi trực tiếp `viz.setScale()` và `save()`, không chạy qua toàn bộ chu trình `applySettings()`.
    5. **Xóa `viz.invalidate()` thừa** khỏi `applySettings()`.
    6. **Nâng cấp Cache**: `mashloop-v73` trong `web/sw.js` và `?v=73` trong `web/index.html`. Đồng bộ toàn bộ tài nguyên sang `dist/MashLoop/_internal/web/`.
    7. **Kiểm thử tự động**: Viết test suite `test_viz_scaling_and_glow_stability()` trong `tests/test_server_and_features.py` (Toàn bộ 19 test suites passed, Exit Code 0).

- **Tính năng kéo thả trực tiếp tại mép giao diện (Edge Resizer) & Tinh chỉnh tỷ lệ Visualizer / UI Scale**:
  - **Bối cảnh & Yêu cầu**:
    1. Người dùng yêu cầu không dùng thanh kéo slider trong cài đặt để chỉnh độ rộng panel, mà cho phép đưa chuột vào mép giao giữa Stage và Panel để kéo thả trực tiếp.
    2. Cung cấp thanh trượt tinh chỉnh kích thước/tỷ lệ các thành phần (Visualizer Canvas và Zoom giao diện UI).
    3. Tránh hoàn toàn việc vỡ layout 2 cột (Stage trái, Panel phải).
  - **Triển khai**:
    1. **Edge Resizer trực tiếp (`#panel-resizer`)**:
       - Đặt thẻ `<div class="panel__resizer" id="panel-resizer"></div>` bên trong `<aside class="panel">` với `position: absolute; left: 0; transform: translateX(-50%); width: 14px;`.
       - Giữ nguyên cấu trúc CSS Grid `<main class="layout">` chỉ có đúng 2 phần tử con trực tiếp (`.stage` và `.panel`), ngăn chặn triệt để lỗi grid wrapping xuống dòng dọc.
       - Hỗ trợ đầy đủ sự kiện chuột và cảm ứng (`mousedown`, `mousemove`, `mouseup`, `touchstart`, `touchmove`, `touchend`).
       - Thêm sự kiện `dblclick` để reset độ rộng panel về mặc định 420px.
       - Giới hạn kéo thả an toàn: `minWidth = 320px`, `maxWidth = Math.min(720px, window.innerWidth * 0.6)`.
       - Hiệu ứng thị giác: Khi hover hiển thị con trỏ `col-resize` và thanh sáng neon tím dọc ranh giới.
    2. **Thanh trượt tỷ lệ Visualizer & Zoom UI trong tab Tinh chỉnh**:
       - `#s-viz-scale`: Phạm vi 70% – 130%, kết nối trực tiếp `viz.setScale()` trong `web/js/viz.js`.
       - `#s-ui-scale`: Phạm vi 80% – 125%, kết nối biến CSS `--ui-scale` và kích thước font gốc trên `document.documentElement`.
       - Toàn bộ giá trị tự động lưu vào `localStorage` và gửi đồng bộ lên server `/api/settings`.
    3. **Nâng cấp Cache**: `mashloop-v72` trong `web/sw.js` và `?v=72` trong `web/index.html`. Đồng bộ toàn bộ tài nguyên sang `dist/MashLoop/_internal/web/`.
    4. **Kiểm thử tự động**: Chạy toàn bộ 18 test suites trong `tests/test_server_and_features.py` đạt **Exit Code 0**. Đã commit và push GitHub (`d6f4d08`).

- **Khắc phục lỗi toàn bộ tham số, cài đặt và playlist bị reset về mặc định khi tải lại web (Settings Persistence Fix)**:
  - **Nguyên nhân gốc rễ**:
    1. Trong `web/js/main.js` (line 265 cũ), hàm `save()` gọi `JSON.stringify({ v: SETTINGS_VERSION, ui, player: player.settings })`. Tuy nhiên, biến `SETTINGS_VERSION` không hề được khai báo trong codebase (`ReferenceError: SETTINGS_VERSION is not defined`).
    2. Do hàm `save()` bọc trong `try ... catch (_) { /* storage unavailable */ }`, lỗi `ReferenceError` bị nuốt chửng âm thầm (vi phạm nguyên tắc *Fail Loudly*).
    3. Kết quả: Bất kỳ thay đổi nào của người dùng (âm lượng, giao diện màu sắc, độ sáng neon, thời gian ở lại dwell min/max, tần suất nhảy, bộ lọc chuyển bài cut/drop/blend..., độ đa dạng, danh sách kho nhạc, v.v.) đều **không bao giờ được ghi vào `localStorage`**. Mỗi khi F5 hoặc tải lại trang web, `localStorage.getItem("loopbox.settings.v1")` luôn trả về `null` khiến toàn bộ tham số bị reset về mặc định gốc.
    4. Thêm vào đó: switch `#s-tempo` thiếu `addEventListener`; các trạng thái `activePlaylistId`, `lockToPlaylist`, `libSortMode`, `activeTab` chưa được liên kết đồng bộ vào `ui`.
  - **Khắc phục**:
    1. **Khai báo chuẩn xác `SETTINGS_VERSION = 2`** trong `web/js/main.js`.
    2. **Đồng bộ toàn diện cấu hình vào `ui`**:
       - Bổ sung `activePlaylistId`, `lockToPlaylist`, `libSortMode`, `activeTab` vào đối tượng `ui`.
       - Lưu vào `localStorage` lập tức khi người dùng click chip playlist, đổi kiểu sắp xếp (sort), chuyển tab (library/settings) hoặc toggle chế độ lock.
       - Tự động khôi phục đúng tab đang đứng và sắp xếp thư viện khi tải lại trang web.
    3. **Bổ sung API lưu trữ trên server backend (`/api/settings`)**:
       - Tạo 2 endpoint `GET /api/settings` và `POST /api/settings` trong `loopbox/server.py` lưu file `data/settings.json`.
       - Đồng bộ 2 chiều: Client lưu nhanh vào `localStorage` (phản hồi tức thì 0ms, không lag giao diện) và tự động debounce gửi bản sao lên server (`data/settings.json`) để đồng bộ xuyên suốt giữa Web browser và Desktop App.
    4. **Bổ sung event listener cho switch `#s-tempo`** để ghi nhận và lưu cài đặt đồng bộ tempo.
    5. **Nâng cấp Cache**: `mashloop-v70` trong `web/sw.js` và `?v=70` trong `web/index.html`. Đồng bộ tài nguyên sang `dist/MashLoop/_internal/web/`.
    6. **Kiểm thử tự động**: Viết test suite `test_settings_api_and_client_persistence()` trong `tests/test_server_and_features.py` (Toàn bộ 18 test suites passed, Exit Code 0). Đã commit và push GitHub (`c3eecf0`).

- **Khắc phục lỗi worker bị dừng xử lý hàng đợi (ProcessPoolExecutor Deadlock on Windows)**:
  - **Nguyên nhân gốc rễ**: Khi thêm `max_tasks_per_child = 3` vào `ProcessPoolExecutor`, trên môi trường Windows (`mp_context="spawn"`), tiến trình con sau khi hoàn thành 3 tác vụ sẽ tự thoát để hệ thống spawn tiến trình mới. Tuy nhiên trên Windows, luồng quản lý hàng đợi `_queue_management_worker` của Python gặp tình trạng deadlock với pipe IPC sau 3 chu kỳ tái sinh (đúng 9 tác vụ) khiến hàng đợi dừng lại hoàn toàn, các bài còn lại bị kẹt ở trạng thái `đang chờ · 0%`.
  - **Khắc phục**:
    1. Gỡ bỏ `max_tasks_per_child` khỏi `_pool()` trong `loopbox/worker.py`. Sử dụng cơ chế dọn dẹp bộ nhớ an toàn đã có sẵn: `gc.collect()` và `torch.cuda.empty_cache()` sau mỗi bài hát trong `loopbox/ingest.py`.
    2. Sửa lỗi thiếu `import { isMobile }` trong `web/js/main.js` gây `ReferenceError` làm gián đoạn render danh sách bài hát.
    3. Khôi phục `TARGET_LUFS = -14.0` trong `loopbox/config.py`.
    4. Nâng cấp cache lên `mashloop-v69`. Toàn bộ hàng đợi 31 bài tiếp tục được xử lý mượt mà liên tục (Exit Code 0).
- **Khắc phục lỗi WebKit Crash và tự động tải lại trang khi bấm chuyển bài trên di động (Mobile iOS Jetsam OOM Crash)**:
  - **Nguyên nhân gốc rễ**:
    1. **Định dạng PCM Float32 trong Web Audio API tốn rất nhiều RAM**: Mỗi phút âm thanh Stereo 44.1kHz khi giải mã bằng `ctx.decodeAudioData(audio)` cần: `60s * 44100 * 2 channels * 4 bytes = 21.16 MB` RAM.
    2. Một bài hát thông thường 3-4 phút chỉ tốn ~60-80 MB RAM. Tuy nhiên, thư viện của người dùng có chứa các video mixtape/tổng hợp dài từ 35 đến 52 phút (ví dụ track `9A_yIFtmAEc` dài 3120 giây ~ 52 phút).
    3. Khi giải mã track 52 phút này, Web Audio cần cấp phát **hơn 1.1 GB RAM bộ đệm uncompressed PCM** (nếu cộng thêm vocal stem thì lên tới 2.2 GB).
    4. Trên thiết bị di động (đặc biệt là iOS Safari / WebKit), hệ điều hành có tiến trình giám sát bộ nhớ Jetsam. Bất kỳ tiến trình tab web nào vượt ngưỡng ~500MB - 800MB đều bị Jetsam lập tức buộc dừng (OOM terminate), khiến trình duyệt xuất hiện thông báo tải lại trang web hoặc quay về trạng thái ban đầu ("Hai vòng đang chờ").
    5. Cấu hình backend `MAX_DURATION_S` trước đó đặt mặc định là 60 phút (`60 * 60`), cho phép nạp nguyên các video mixtape tổng hợp dài hàng giờ vào trình phát nhạc vốn thiết kế cho bài hát.
  - **Khắc phục**:
    1. **Giới hạn thời lượng Backend (`loopbox/config.py`)**: Đặt `MAX_DURATION_S = 15 * 60` (15 phút). Bất kỳ video mixtape dài hơn 15 phút sẽ bị từ chối ngay khi tải với thông báo rõ ràng: "dài hơn 15 phút (xx phút), không thể phân tích phách nhịp".
    2. **Chốt chặn bộ nhớ Frontend (`web/js/api.js`)**:
       - Thêm `isMobile` và ngưỡng an toàn `MAX_SAFE_DURATION_S` (12 phút trên mobile, 20 phút trên desktop).
       - Trong `Loader.get(id)` và `Loader.vocals(id)`: Nếu thời lượng bài vượt quá giới hạn an toàn, từ chối giải mã trước khi gọi `ctx.decodeAudioData` và bắn lỗi cảnh báo `Bài quá dài (xx phút) không thể nạp vào bộ nhớ thiết bị`.
       - Giới hạn bộ đệm giữ trong RAM trên mobile `this.keep = 2`.
    3. **Bộ lập lịch chuyển bài an toàn (`web/js/player.js`)**:
       - Trên di động, giảm số bài prefetch từ 3 xuống 1 bài để tiết kiệm RAM.
       - Trong `_usable(T, tr)`: Tự động loại bỏ các bài quá dài khỏi danh sách ứng viên chuyển bài, ngăn chain planner tự ý chọn các bài gây tràn RAM.
       - Trong `_setPlan`: Nếu tải bài thất bại, đánh dấu `best.tr.failed = true` và phát sự kiện `plan-failed` thay vì thử lại vô tận.
       - Trong `setTargetNext(id)`: Chặn ghim bài kế tiếp nếu bài đó vượt quá thời lượng an toàn cho phép.
    4. **Giao diện & Cảnh báo người dùng (`web/js/main.js`)**:
       - Đánh dấu icon cảnh báo `⚠️` màu vàng cam trên danh sách bài hát đối với các bài quá dài.
       - Đón sự kiện `plan-failed` để hiển thị modal giải thích lý do không thể chuyển bài.
    5. **Nâng cấp Cache**: `mashloop-v67` trong `web/sw.js` và `?v=67` trong `web/index.html`.
    6. **Kiểm thử tự động**: Bổ sung `test_max_duration_guard_and_frontend_limits()` vào `tests/test_server_and_features.py` (Toàn bộ 17 test suites passed, Exit Code 0).
- **Khắc phục lỗi nạp nhạc YouTube (`Requested format is not available` / 403) và lỗi crash 500 khi hủy/xóa bài (`TypeError: in_use()`)**:
  - **Nguyên nhân gốc rễ**:
    1. **Crash khi hủy/xóa bài (`TypeError`)**: Trong `loopbox/server.py` (lines 406 & 419), code gọi `sessions.in_use(tid)`. Tuy nhiên, định nghĩa `def in_use()` trong `loopbox/sessions.py` không nhận đối số vị trí (`takes 0 positional arguments but 1 was given`). Khi chạy trên Hugging Face Space (`MULTIUSER = True`), thao tác xóa bài gây lỗi HTTP 500 Unhandled Exception khiến lệnh xóa và hủy ngầm `worker.cancel(tid)` không được thực thi; các luồng tải tiếp tục chạy ngầm trong background và sinh log lỗi liên tục.
    2. **Lỗi `Requested format is not available` trên YouTube**:
       - Trên YouTube hiện nay, các client `web`, `mweb`, `web_embedded` bắt buộc phải có Proof-of-Origin (PO) Token. Thiếu token này, `yt-dlp` tự động bỏ qua toàn bộ luồng stream âm thanh/video và chỉ giữ lại ảnh thumbnail/storyboard. Khi `yt-dlp` áp dụng bộ lọc `format="bestaudio/best"`, nó không tìm thấy format nào phù hợp và báo lỗi `Requested format is not available`.
       - Format 251 (Opus) trực tiếp từ visionos bị chặn 403 Forbidden nếu không có cờ `missing_pot` hoặc cấu hình format dự phòng. Trong khi đó, luồng HLS (`format 233`, `234`) và `android_vr` hoạt động ổn định 100%.
       - Thiếu `ffmpeg` trên container Hugging Face do `packages.txt` trước đó chưa được đưa vào `ALLOW_PATTERNS`.
  - **Khắc phục**:
    1. Cập nhật `sessions.in_use(tid: str | None = None)`: Trả về `bool` (`tid in all_used`) nếu truyền `tid`, hoặc `set[str]` nếu gọi không đối số. Thao tác xóa và hủy bài hoạt động trơn tru trong cả single-user và multi-user mode.
    2. Trong `loopbox/download.py`:
       - Bổ sung cờ `'formats': ['missing_pot']` vào `extractor_args['youtube']` để ngăn `yt-dlp` loại bỏ các luồng thiếu PO-token.
       - Cập nhật format selector thành `"bestaudio/b[acodec!=none]/ba/best[acodec!=none]/best/all"`, tự động fallback sang các format âm thanh khả dụng (như HLS mp4 233/234 hoặc format 18) khi direct DASH format 251 bị 403.
       - Chuẩn hóa thứ tự ưu tiên `YOUTUBE_CLIENT_CONFIGS`: `visionos` -> `visionos + android_vr` -> `android_vr` -> `web_music + web` -> `web` -> `None`.
       - Dọn dẹp `_find_js_runtimes()`: Chỉ đăng ký các runtime JS thực sự tồn tại trên máy (tránh tạo ghost entry `{}`).
    3. Bổ sung `_ensure_ffmpeg()` trong `app.py`, thêm `imageio-ffmpeg` vào `requirements.txt` và đưa `packages.txt` vào `tools/upload_to_space.py` để container Space luôn có `ffmpeg`.
    4. Cập nhật bộ unit test `tests/test_server_and_features.py` bao quát cả trường hợp `MULTIUSER = True` khi xóa và batch xóa (Exit Code 0). Đã commit, push GitHub (`8d6ac1c`) và deploy Space container reboot (`efda80b`).
- **Khắc phục lỗi tác vụ tải ngầm tiếp tục chạy và sinh lỗi khi người dùng đã chủ động xóa bài**:
  - **Nguyên nhân gốc rễ**: Khi người dùng nhấn nút "Xóa" hoặc "Xóa theo lô" (chọn tất cả và xóa), endpoint `DELETE /api/tracks/{tid}` và `POST /api/tracks/batch` (`action="delete"`) trước đó chỉ xóa id bài hát khỏi danh sách session trong SQLite/RAM. Trong khi đó, worker ngầm `ProcessPoolExecutor` vẫn tiếp tục download và phân tích các bài hát cũ từ phiên nạp trước; các tiến trình con không hề nhận được tín hiệu hủy, dẫn đến việc tiếp tục download, gặp lỗi mạng/cookie cũ và sinh log lỗi liên tục. Hơn nữa khi người dùng nạp lại playlist, `register()` thấy bài hát cũ vẫn đang ở trạng thái `queued`/`downloading` nên không tạo mới.
  - **Khắc phục**:
    1. **Cơ chế Hủy Tác Vụ Ngay Lập Tức (Immediate Job Cancellation)**:
       - Bổ sung `library.mark_cancelled(tid)`: Tạo file cờ sentinel `data/library/{tid}.cancel` và xóa ngay thư mục metadata/sound của bài.
       - Bổ sung `worker.cancel(tid)` và `worker.cancel_many(tids)`: Rút tác vụ khỏi danh sách `_ingesting`, hủy future (`fut.cancel()`) trong `ProcessPoolExecutor`.
       - Trong `download.download()`, hook tải về kiểm tra `library.is_cancelled(tid)` trên từng chunk nhận được. Nếu bài đã bị xóa, lập tức `raise RuntimeError("Đã huỷ nạp bài theo yêu cầu")` để ngắt ngay socket kết nối của yt-dlp, không tải thừa bất kỳ byte nào.
       - Trong `ingest.process()`, kiểm tra hủy trước/sau khi download và convert; chặn toàn bộ log cảnh báo lỗi đối với các bài đã bị hủy chủ động.
       - Trong `server.py`, cập nhật cả 2 endpoint xóa đơn lẻ và xóa theo lô để kích hoạt `worker.cancel()` và `library.delete()` ngay lập tức.
    2. **Khắc phục triệt để lỗi "Requested format is not available" & Xác minh bot YouTube**:
       - Đưa tổ hợp client `["visionos", "tv_downgraded", "android", "web"]` lên vị trí ưu tiên số 1 trong cả `download()` và `resolve()`. Client `visionos` hoàn toàn miễn nhiễm với cơ chế chặn SABR và thử thách bot của YouTube, đồng thời `tv_downgraded` và `android` cung cấp đầy đủ format âm thanh AAC/Opus chất lượng cao cho yt-dlp.
    3. **Nâng cấp Cache hệ thống**: `mashloop-v66` trong `web/sw.js` và `?v=66` trong `web/index.html`. Nâng tổng số bài kiểm thử lên 16/16 test suites (Exit Code 0).
- **Khắc phục lỗi xác minh bot YouTube & mất cookie khi Space container khởi động lại**:
  - **Nguyên nhân gốc rễ**:
    1. Cấu hình `BASE_OPTS` trong `loopbox/download.py` trước đó bị gán cứng `player_client: ["web_embedded", "android", "web"]`. Khi gọi YouTube trên IP datacenter (như Hugging Face Spaces), client này bị YouTube kích hoạt cơ chế chống bot và thử nghiệm SABR, khiến số format tụt từ 43 format xuống 5 format (không có stream audio) -> báo lỗi `Sign in to confirm you're not a bot`.
    2. Hugging Face Space là container vô trạng thái (ephemeral container). Khi container khởi động lại hoặc build mới, thư mục `data/` bị xóa sạch khiến file `data/cookies.txt` biến mất, dẫn đến việc yt-dlp không còn cookie xác thực.
    3. Trong `app.py`, điều kiện đồng bộ code từ GitHub chỉ kiểm tra `if (ROOT / "loopbox" / "server.py").exists()`, dẫn đến việc khi container restart mà không rebuild, code mới nhất từ GitHub không được kéo về.
  - **Khắc phục**:
    1. **Tối ưu hóa Client yt-dlp**: Xóa bỏ hoàn toàn cấu hình ép client cứng trong `BASE_OPTS`. Trong `resolve()` và `download()`, ưu tiên `None` (cơ chế nhận diện mặc định của yt-dlp với visionos + web — đã kiểm chứng thực tế cho 43 format đầy đủ), sau đó mới fallback sang `android`, `web`, `tv_downgraded`, `mweb`.
    2. **Hỗ trợ nạp Cookie vĩnh viễn qua Space Secret**: Bổ sung hỗ trợ biến môi trường `YOUTUBE_COOKIES` / `COOKIES_TXT` trong cả `loopbox/cookies.py` và `app.py`. Người dùng chỉ cần thêm Secret trên Space Settings là cookie được tự động nạp mỗi khi container khởi động, không bao giờ bị mất.
    3. **Sửa cơ chế đồng bộ code trên Space**: `app.py` luôn đồng bộ phiên bản mới nhất từ GitHub private repository khi chạy trên Hugging Face (`SPACE_ID` present).
    4. **Nâng cấp Cache hệ thống**: `mashloop-v65` trong `web/sw.js` và `?v=65` trong `web/index.html`.
- **Khắc phục lỗi không chuyển được playlist khi click vào chip playlist**:
  - **Nguyên nhân gốc rễ**: Khi sửa lỗi cuộn nhảy giật ở turn trước, dòng lệnh gán `activePlaylistId = chip.dataset.plId;` trong sự kiện click `#pl-chips` vô tình bị thiếu, khiến trạng thái playlist luôn giữ ở `"all"` và không đổi danh sách bài hát.
  - **Khắc phục**: Khôi phục `activePlaylistId = chip.dataset.plId;` đồng thời giữ nguyên cơ chế cuộn ngang `scrollChipIntoView()`. Nâng cấp Cache lên `mashloop-v65`.
- **Khắc phục lỗi thanh cuộn tự động nhảy giật lên đầu trang khi đang cuộn**:
  - **Nguyên nhân gốc rễ**:
    - Trong hàm `renderPlaylistChips()` tại `web/js/main.js`, tồn tại lệnh `onChip.scrollIntoView({ behavior: "smooth", inline: "nearest", block: "nearest" })`.
    - Khi có bài hát đang nạp/tải hoặc polling mỗi 1.2s, hàm `renderLibrary()` được gọi liên tục. Mỗi lần chạy, `onChip.scrollIntoView()` lại ép toàn bộ container cha (`.panel`, `window`) cuộn ngược lên đầu trang để hiển thị chip playlist đang chọn.
  - **Khắc phục**:
    - Xóa bỏ hoàn toàn lệnh `scrollIntoView()` toàn cục trên chip playlist.
    - Xây dựng hàm `scrollChipIntoView(container, chip)` tính toán tọa độ tương đối và chỉ điều khiển thuộc tính cuộn ngang cục bộ `container.scrollLeft`, tuyệt đối không làm ảnh hưởng đến vị trí cuộn dọc của trang.
    - Thêm bộ nhớ đệm `lastChipsHtml` để không bao giờ ghi đè DOM `#pl-chips` nếu danh sách playlist không thay đổi.
    - Nâng cấp Cache hệ thống lên `mashloop-v63` trong `web/sw.js` và `?v=63` trong `web/index.html`.
- **Khắc phục lỗi "Requested format is not available" & Xác minh bot YouTube trên Cloud/Local**:
  - **Nguyên nhân gốc rễ**:
    1. Danh sách `clients` trong `resolve()` và `download()` trước đó chỉ xoay vòng quanh `web_embedded` và `mweb`, không bao giờ thử client chuẩn mặc định (`None`) hay `["android", "web"]`. Khi người dùng nạp cookie, YouTube áp dụng SABR trên `web_embedded`, khiến yt-dlp chỉ nhận diện ảnh storyboard (0 format âm thanh/video) -> `Requested format is not available`.
    2. Trên môi trường đám mây Hugging Face Space (Gradio image), hệ thống hoàn toàn thiếu Javascript engine (không có Node lẫn Deno). Khi yt-dlp gặp thử thách `n-sig challenge`, do không giải mã được chữ ký nên YouTube tước bỏ mọi luồng audio.
  - **Khắc phục**:
    1. Đưa `None` (cấu hình mặc định tự thích ứng của yt-dlp), `["android", "web"]`, `["web_embedded", "android", "web"]`, và `["mweb"]` vào chuỗi fallback của cả `resolve()` và `download()`.
    2. Tích hợp cơ chế tự động cài đặt Deno `_ensure_deno()` trong `app.py`: Tự động tải standalone binary Deno (35MB) trên Linux container khi khởi động, đưa vào PATH để yt-dlp giải mã chữ ký n-sig 100%.
    3. Đã khởi động lại server local chạy nền trên `0.0.0.0:8765` (PID: 32188).
- **Triển khai Kiến trúc Giấu Mã Nguồn Tuyệt Đối trên Hugging Face Spaces (Private Code Loader)**:
  - **Mục tiêu**: Người dùng muốn repo Space để Public (để web app `https://m3ik18dp-mashloop.hf.space` ai cũng dùng được), nhưng giấu 100% mã nguồn dự án (`loopbox/`, `web/`) và xóa sạch lịch sử commit cũ trên Space.
  - **Triển khai**:
    1. **Dynamic Private Code Loader (`app.py`)**: Khi Space khởi động, `_sync_private_code()` đọc secret `GH_TOKEN` trên Space, tải zipball trực tiếp từ GitHub API của repo private `m3iK18dp/mashloop`, giải nén `loopbox/` và `web/` thẳng vào RAM/container mà không lưu mã nguồn vào repo Space.
    2. **Xóa sổ toàn bộ commit cũ trên Hugging Face Space**: Tạo root commit duy nhất `5945d2f`, force push (`git push --force`) đè toàn bộ git history trên Space. Space hiện chỉ có duy nhất 1 commit và đúng 4 file vỏ bọc: `app.py`, `requirements.txt`, `README.md`, `.gitignore`. Không còn bất kỳ file source code nào trong cây git của Space.
    3. **Cấu hình `tools/upload_to_space.py`**: Khóa cứng `allow_patterns = ["app.py", "requirements.txt", ".gitignore"]`, ngăn chặn vĩnh viễn việc upload nhầm file mã nguồn lên Space trong tương lai.
    4. **Kiểm thử**: Space chuyển sang `STAGE: RUNNING`, `https://m3ik18dp-mashloop.hf.space` trả về HTTP 200, `/api/cookies` trả về HTTP 200.
- **Kiểm chứng tải thực tế YouTube với Cookie Fallback**:
  - Đã chạy test thực tế tải URL video YouTube (`fAafG7BPznQ`) với cookie đang bật: Cơ chế fallback hoạt động chuẩn xác, tải trọn vẹn file 285 MB thành công (Exit Code 0).
- **Sửa lỗi thụt dòng nghiêm trọng trong `download()` — Cookie fallback không hoạt động**:
  - Nguyên nhân gốc: Khối `try/except` (lines 531-558) của `download()` trong `loopbox/download.py` bị thụt ra **ngoài** vòng lặp `for client in clients:`. Hệ quả: chỉ cấu hình client cuối cùng được thực thi, cơ chế xoay vòng client và fallback không-cookie hoàn toàn vô hiệu.
  - Khắc phục: Thụt toàn bộ `try/except` vào đúng trong `for client` loop. Đổi `cookie_passes` mặc định từ `[False]` sang `[True]` khi không có cookie.
  - Kiểm thử: 15/15 test suites đạt Exit Code 0.
- **Khắc phục lỗi YouTube SABR Stream & Cơ chế Fallback Hai Lớp Cho Cookie (`Requested format is not available`)**:
  - Tìm ra nguyên nhân gốc rễ:
    1. Khi người dùng nạp cookie tài khoản YouTube cá nhân, YouTube áp dụng thử nghiệm streaming SABR (Server-side Adaptive Bitrate) trên phiên đăng nhập. Do thiếu Web PO-Token (Proof of Origin), `yt-dlp` bị YouTube tước bỏ toàn bộ luồng stream âm thanh/video thông thường, chỉ trả về dạng ảnh/storyboard, dẫn đến lỗi `Requested format is not available. Use --list-formats...`.
    2. Trong khi đó, nếu tải ở chế độ khách vãng lai (không cookie), video (như `fAafG7BPznQ`) lại trả về luồng âm thanh Opus chất lượng cao (format 251) bình thường 100%!
    3. Video `K28OXlBknjc` ("MIXTAPE KHANG RỒNG") thực tế đã bị gỡ/không khả dụng trên YouTube (`This video is unavailable`).
  - Giải pháp triển khai:
    - **Cơ chế Fallback Hai Lớp (`cookie_passes`) trong `loopbox/download.py`**: Áp dụng cho cả hàm `resolve()` và `download()`. Lớp 1 thử nạp với cookie người dùng (giải quyết video giới hạn độ tuổi, bot check). Nếu YouTube trả lỗi `DownloadError` (SABR, `Requested format is not available`, bot token...), hệ thống tự động fallback tức thì sang Lớp 2 (không dùng cookie) mà không làm gián đoạn người dùng.
    - **Chuẩn hóa thông báo lỗi (`clean_error`)**: Thêm nhánh nhận diện `requested format is not available` -> *"Video không khả dụng hoặc định dạng bị hạn chế"*; `this video is unavailable` -> *"Video này không khả dụng hoặc đã bị tác giả gỡ trên YouTube"*.
- **Thêm biểu tượng SVG xinh xắn cho nút chuyển Tab Bảng điều khiển (`.seg.tabs`)**:
  - Bổ sung biểu tượng SVG sắc nét đồng bộ phong cách tối giản cho 2 nút chuyển đổi tab Bảng điều khiển:
    - Tab **Thư viện** (`data-tab="library"`): Icon nốt nhạc đôi thanh thoát (`music notes` 13px) biểu thị kho bài hát.
    - Tab **Tinh chỉnh** (`data-tab="settings"`): Icon cần gạt âm thanh / fader mixer (`sliders` 13px) biểu thị bảng điều chỉnh và hiệu ứng DJ.
  - Tự động đổi màu tương phản (`currentColor`) khi được chọn trên nền cam/hổ phách accent hoặc mờ êm dịu khi chưa kích hoạt.
  - Nâng cấp phiên bản Cache hệ thống: `mashloop-v62` trong `web/sw.js` và `?v=62` trong `web/index.html`.
- **Hệ thống Quản lý Cookie Nguồn nhạc (Port từ EveryThingDownloader)**:
  - Tích hợp module `loopbox/cookies.py`: Hỗ trợ nạp cookie định dạng chuẩn **Netscape** (`cookies.txt` từ tiện ích *Get cookies.txt LOCALLY*) và **JSON** (từ tiện ích *J2TEAM Cookies*).
  - Tự động phát hiện và gia hạn session/zero-timestamp cookies thêm 1 năm để tránh bị `http.cookiejar` / `yt-dlp` loại bỏ trước khi gửi request tới YouTube.
  - Tự động lưu trữ an toàn tại `DATA_DIR / "cookies.txt"` và tự động truyền cờ `opts["cookiefile"]` vào mọi yêu cầu tải/phân tích bài hát trong `loopbox/download.py`.
  - Bổ sung 3 API endpoints backend: `GET /api/cookies`, `POST /api/cookies`, `DELETE /api/cookies`.
  - Giao diện người dùng tối giản trong Cài đặt: Thẻ trạng thái cookie nhỏ gọn, biểu tượng SVG trực quan (Tải file, Dán mã, Xóa), dialog dán mã cookies tức thì (`#cookie-modal`).
- **Thanh điều hướng cuộn thông minh cho Playlist (`#pl-chips`)**:
  - Khắc phục lỗi tràn danh sách khi có nhiều playlist trên desktop: Bổ sung 2 nút mũi tên SVG điều hướng trái/phải (`#pl-scroll-left`, `#pl-scroll-right`) ẩn trên màn hình nhỏ di động.
  - Chuyển đổi lăn chuột dọc thành cuộn ngang (`wheel` -> `scrollLeft`) khi trỏ chuột vào danh sách playlist.
  - Thiết kế thanh cuộn micro-scrollbar siêu mỏng 3px tinh tế (`scrollbar-width: thin`), nổi bật khi rê chuột.
  - Cắt ngắn tiêu đề playlist quá dài (`max-width: 150px`, `text-overflow: ellipsis`) kèm tooltip `title` đầy đủ.
  - Tự động cuộn playlist đang chọn vào trung tâm tầm nhìn (`scrollIntoView({ inline: "nearest" })`).
- **Khắc phục lỗi mục "Thư viện" trơ trọi không có nội dung trong Cài đặt**:
  - Nguyên nhân gốc: Khi chạy ở chế độ nhiều người dùng (Hugging Face Spaces), mã JS chỉ ẩn nút `#btn-relink` (`$("#btn-relink").hidden = true`), để lại thẻ cha `<section>` và tiêu đề `<h2>Thư viện</h2>` đứng một mình với khoảng đệm trống.
  - Khắc phục: Gán định danh `id="group-relink"` cho toàn bộ section và ẩn toàn bộ phần này khi `session.multiuser` kích hoạt.
- **Tối giản hóa văn bản & Tăng cường SVG theo yêu cầu người dùng**:
  - Hạn chế tối đa chữ rườm rà, thay thế bằng biểu tượng SVG sắc nét, đồng bộ phong cách tối giản hiện đại.
  - Nâng cấp phiên bản Cache hệ thống: `mashloop-v61` trong `web/sw.js` và `?v=61` trong `web/index.html`.
- **Khảo sát giải pháp của dự án EveryThingDownloader & Triển khai toàn diện cho MashLoop**:
  - Đối chiếu mã nguồn EveryThingDownloader (`D:\JOB\DEV\EveryThingDownloader`): Dự án này tải mượt trên Docker/Cloud nhờ 4 yếu tố cốt lõi mà MashLoop trước đó còn thiếu:
    1. **Giả lập TLS Fingerprint bằng `curl-cffi` (`impersonate="chrome"`)**: YouTube và Cloudflare kiểm tra ciphers và TLS ClientHello (JA3/JA4). Python urllib/OpenSSL bị nhận diện ngay là bot datacenter. Cài `curl-cffi>=0.15.0` và tích hợp `ImpersonateTarget.from_str("chrome")` biến mọi kết nối tới YouTube mang TLS fingerprint của trình duyệt Chrome thật 100%.
    2. **Tích hợp Deno JS Engine vào Docker container**: Dockerfile cũ của MashLoop không có Node lẫn Deno, khiến yt-dlp trên Hugging Face Space không thể giải mã n-sig signature của YouTube. Bổ sung `COPY --from=denoland/deno:bin /deno /usr/local/bin/deno` vào `Dockerfile` (nhẹ ~80MB, binary độc lập, không phụ thuộc apt) để yt-dlp giải mã chữ ký YouTube tức thì.
    3. **Ưu tiên client `web_embedded`**: Chuyển cấu hình `player_client` sang `["web_embedded", "android", "web"]`. Client `web_embedded` mô phỏng trình phát nhúng web bên thứ ba, không bị áp cơ chế kiểm duyệt bot ngặt nghèo của IP datacenter.
    4. **Tự động nhận diện `cookies.txt`**: Bổ sung cơ chế tự động nạp file `cookies.txt` nếu có tại thư mục dữ liệu hoặc root.
- **Bypass chặn tải YouTube trên IP Datacenter (Hugging Face Spaces) & Tự động quay vòng client**:
  - Tìm ra nguyên nhân gốc: Trên máy chủ đám mây, client `android` mặc định của `yt-dlp` bị chặn bởi hệ thống bot check của YouTube (`Sign in to confirm you're not a bot`). Khi chuyển sang client thứ 2 (`ios`), YouTube trả về lỗi định dạng luồng stream SABR. Do thông báo lỗi từ `ios` không chứa chữ `bot` hay `403`, điều kiện cũ trong mã đã `raise` vội vã và dừng hẳn toàn bộ tiến trình tải, không bao giờ thử tới `mweb` hay `web`!
  - Cấu hình ưu tiên `player_client: ["mweb", "android", "ios", "web"]` trong `BASE_OPTS`. Khi tải qua `mweb`, YouTube không áp đặt cơ chế xác thực tài khoản và trả về định dạng âm thanh nhanh chóng.
  - Xây dựng vòng lặp xoay vòng client đa tầng (`mweb-first`, `android`, `web`, `tv_embedded`) cho cả `resolve()` và `download()`: nếu bất kỳ client nào gặp sự cố (bot check, format error, token hết hạn), hệ thống tự động thử tiếp cấu hình client kế tiếp mà không crash đột ngột.
- **Tối ưu hiển thị lỗi trên giao diện bài hát (Clean Error Display & Line Clamping)**:
  - Khắc phục lỗi hiển thị các đoạn log terminal dài hơn 500 ký tự (chứa cờ `--cookies`, đường link wiki GitHub...) làm phình to biến dạng thẻ bài hát:
    - **Backend (`loopbox/ingest.py`)**: Thay thế việc lưu trực tiếp chuỗi exception thô bằng `download.clean_error(e)`. Chuỗi lỗi được chuẩn hóa súc tích, loại bỏ URL, cờ cookies và tiền tố tên lớp ngoại lệ.
    - **Frontend (`web/js/main.js`)**: Bọc dữ liệu `m.error` qua hàm `cleanUiError()` trước khi render vào thẻ `.track .s.err`. Giữ toàn văn thông báo trong thuộc tính `title` để người dùng có thể hover xem khi cần.
    - **CSS (`web/css/app.css`)**: Thiết lập `-webkit-line-clamp: 2`, `display: -webkit-box`, `overflow: hidden`, `text-overflow: ellipsis`, và `max-height: 2.8em` cho `.track .s.err`, khóa cứng lỗi tối đa 2 dòng thẩm mỹ, triệt tiêu hiện tượng vỡ khung danh sách bài hát.
- **Nâng cấp phiên bản Cache hệ thống**: `mashloop-v60` trong `web/sw.js` và `?v=60` trong `web/index.html`.
- **Khôi phục nút Chế độ đêm & Cấu hình theo múi giờ Việt Nam (UTC+7, sau 21h tối)**:
  - Tích hợp hàm `getVietnamHour()` chuẩn `Asia/Ho_Chi_Minh` (với fallback tính `UTC + 7 * 3600000`).
  - Lập lịch hiển thị thông minh `checkNightButtonVisibility()`: Nút [Đêm] (biểu tượng trăng khuyết `#btn-night`) chỉ xuất hiện trên thanh deck sau 9h tối ($21\text{h} - 6\text{h}$ sáng hôm sau). Ban ngày tự động ẩn để giữ thanh deck tinh gọn.
  - Xử lý hành vi kích hoạt toàn diện khi bấm [Đêm]:
    - **Thị giác (Ambient Atmosphere)**: Thêm lớp `.is-night` trên `<body>`, dịu quầng sáng neon (`--glow-mult: 0.38`), hạ sáng phông nền phòng chiếu (`.field`) và visualizer canvas xuống mức êm mắt dịu nhẹ khi nằm nghe trong bóng tối. Nút [Đêm] phát sáng ánh trăng tím dịu (`#a5b4fc`) cùng icon trăng nghiêng $15^\circ$.
    - **Âm thanh (Acoustics)**: Kích hoạt bộ lọc âm đêm dịu `setEq("night")` (cắt bớt dải tần chói gắt để nghe thư giãn).
    - Đồng bộ 2 chiều với menu popover EQ.
- **Sửa lỗi icon Volume SVG bị cắt phẳng lẹm ở cạnh phải**:
  - Tìm ra nguyên nhân gốc: Tọa độ sóng âm ngoài cùng trong `i-vol-high` ban đầu là `M21.5 4.5a10.5 10.5 0 0 1 0 15` bắt đầu từ $x=21.5$, vòng cung nở ra cực đại tại $x=24.65$ (kèm stroke width $1.6\text{px}$ chạm tới $x=25.45$), vượt quá giới hạn `viewBox="0 0 24 24"`, dẫn đến việc bị trình duyệt cắt phẳng một đường dọc ở cạnh phải.
  - Thiết kế lại hệ tọa độ đồng tâm cho cả 4 trạng thái loa (`mute`, `low`, `med`, `high`):
    - Đưa thân loa lùi về $x=2\text{px}$ (`M2 9.5h3.5L10 6v12l-4.5-3.5H2z`).
    - 3 đường sóng âm đồng tâm tại $(7.15, 12)$: Sóng 1 ($x=13.1$), Sóng 2 ($x=17.15$), Sóng 3 cực đại tại $x=21.18\text{px}$.
    - Giữ khoảng cách an toàn $>2\text{px}$ so với biên $x=24$, xóa sổ 100% hiện tượng xén nét. Bổ sung `overflow: visible;` trong CSS.
- **Khắc phục lỗi typographic rớt chữ 1 mình trên dòng mới (Footer Widow/Orphan)**:
  - Khắc phục chữ "nhân." bị rớt lẻ loi xuống dòng 2 trong footer `#fine`:
    - Rút gọn tiêu đề thành *"Mã nguồn mở: Không quảng cáo, không lưu dữ liệu cá&nbsp;nhân."* (ngắn hơn 16 ký tự, nằm trọn trên 1 dòng duy nhất).
    - Thêm khoảng trắng không ngắt `&nbsp;` giữa `cá` và `nhân`.
    - Bổ sung `text-wrap: pretty;` trong `web/css/app.css` để trình duyệt tự động cân đối dòng chữ.
- **Nâng cấp phiên bản Cache hệ thống**: `mashloop-v59` trong `web/sw.js` và `?v=59` trong `web/index.html`.
- **Kiểm thử chuyên sâu & TDD (TDD & Verification Before Completion)**:
  - Bổ sung `test_zen_hud_and_neon_engine` và `test_responsive_mobile_declutter` vào `tests/test_server_and_features.py`.
  - Khảo sát và xác thực toàn diện: Zen HUD, phím tắt `F`/`Esc`, neon luminance engine, dynamic modal sizing, mobile topbar SVGs và cache versioning `v58`.
  - Kết quả kiểm thử: 12/12 test suites đạt tuyệt đối với Exit Code 0.
- **Kiểm tra, tinh gọn chữ và thay thế bằng SVG sạch đẹp (UI Declutter & SVG Polish)**:
  - **Mobile Topbar**: Trên thiết bị di động (`max-width: 520px`) và tablet (`max-width: 768px`), không ẩn `.topbar__end` mà chuyển đổi các nút thao tác thành các nút tròn 30-32px chứa biểu tượng SVG sắc nét (Toàn màn hình Zen, Cài đặt Mobile, Phím tắt & Trợ giúp), ẩn chữ rườm rà.
  - **Nút hành động Playlist & Thao tác**: Thay thế chữ "Phát" thành SVG icon Tam giác Play đồng bộ; nút "Tính lại điểm nối" bổ sung SVG link; nút "Xem bài này" trong bảng phân tích hòa âm chuyển sang icon mũi tên SVG nhỏ gọn.
  - **Rút gọn văn bản khu vực Tải nhạc & Cài đặt**:
    - Khu vực upload: Rút gọn thành *"Tải file nhạc lên - kéo thả file âm thanh hoặc ZIP"*, *"Chọn file"*, *"Chọn thư mục"*.
    - Hướng dẫn nhập: *"Hỗ trợ YouTube, Spotify, SoundCloud, Zing MP3, file âm thanh"*.
    - Nhãn độ sáng: *"Độ sáng neon & đèn"*, mô tả ngắn gọn súc tích.
    - Modal chi tiết bài hát: Rút gọn các nhãn thẻ số liệu thành *"Nhịp điệu"*, *"Tone Camelot"*, *"Thời lượng"*, *"Điểm nhảy"*, *"Điểm nối hòa âm"*.
    - Footer bản quyền: Tinh giản thành *"Phi thương mại & mã nguồn mở: Không quảng cáo, không lưu dữ liệu cá nhân."*
  - Bump cache hệ thống: `mashloop-v58` trong `web/sw.js` và `?v=58` trong `web/index.html`.
- **Khắc phục chữ trong input trên Modal bị to (`.modal-input`, `.pl-modal__create input`)**:
  - Tìm ra nguyên nhân gốc: Rule CSS cũ `input[type="text"], ... .modal-input { font-size: 16px !important; }` (nhằm tránh iOS Safari auto-zoom) đã đè lên mọi clamp font-size của modal, khiến chữ và placeholder trong input to bất thường (16px) lấn át cả tiêu đề và nút bấm.
  - Xóa bỏ selector cưỡng bức 16px toàn cục (thẻ meta viewport đã có `maximum-scale=1` chống zoom an toàn).
  - Khóa font size `.modal-input` và `.pl-modal__create input` chuẩn tỷ lệ `clamp(0.78rem, 2vw, 0.84rem) !important` và placeholder `clamp(0.74rem, 1.9vw, 0.8rem)`, hài hòa 100% với nhãn và nút bấm trên mobile.
- **Toàn màn hình Visualizer & Thanh công cụ HUD tương tác (Zen Fullscreen Canvas Mode)**:
  - Thêm nút chuyển đổi "Toàn màn hình" (`#btn-zen`) trên topbar và hỗ trợ phím tắt `F` (hoặc `Esc` để thoát).
  - Khi kích hoạt: Canvas bung trọn 100vw x 100vh với visualizer siêu nét (SSAA hardware interpolation).
  - Tích hợp thanh công cụ HUD nổi viền neon trên màn hình (`.zen-hud-top` & `.deck`):
    - Góc trái: Tên bài hát, nghệ sĩ, tempo và mood tag thời gian thực.
    - Góc phải: Bộ công cụ DJ nhanh (`Tape` hãm đĩa, `Sweep` quét filter, nút tăng nhanh độ sáng `Neon` 50%→100%→150%→200%), đồng hồ phách và nút đóng `[✕]`.
    - Dưới cùng: Dock điều khiển nổi (Lock, Jump, Play/Pause, Next, Timer, EQ, Volume).
    - Tự động ẩn nhẹ (Inactivity Dimming): Sau 3.5 giây không di chuột/chạm màn hình, các công cụ mờ dần về `opacity: 0.12` để người dùng đắm chìm vào vòng lặp ánh sáng; chạm nhẹ lập tức hiện rõ.
- **Thanh cấu hình độ sáng màu neon ở các nơi trong giao diện (Neon Luminance Engine)**:
  - Cập nhật nhãn và mô tả `#s-glow` trong tab Cài đặt: "Độ sáng màu neon & ánh đèn".
  - Nâng cấp `theme.js` & `app.css`: Thanh trượt điều khiển trực tiếp độ rực (`--acc-c`), độ sáng (`--acc-l`), độ ấm nền (`--gc`), và quầng sáng `--glow-mult` trên toàn bộ giao diện:
    - Biểu tượng Vô cực thương hiệu (`.brand__inf`).
    - Nút bấm, tab đang chọn (`.seg__ind`).
    - Thanh trượt âm lượng và vị trí (`input[type="range"]::-webkit-slider-thumb`).
    - Vạch sáng bài đang phát (`.track.playing::before`).
    - Bụi sáng và ánh nền phòng chiếu (`.field`).
  - Tích hợp hàm `theme.reapply()` và `recolor()` cập nhật tức thì màu neon ngay khi kéo trượt mà không cần đợi đổi bài.
- **Dynamic kích thước các thành phần trên Modal (Responsive Modal System)**:
  - Tinh chỉnh các modal dialog (`.consent`, `#app-modal`, `.mobile-modal`, `.shortcuts-modal`, `.pl-modal`, `.inspect-modal`) với hệ số co giãn linh hoạt (`clamp()`).
  - `.consent`: Thu gọn độ rộng cơ sở về `width: min(410px, calc(100vw - 28px))`, padding mượt `clamp(14px, 3.8vw, 20px)`, bo góc `clamp(12px, 3vw, 16px)`.
  - Heading `.consent h2`: Đổi từ font display to rộng sang `var(--font-text)` với `font: 600 clamp(0.95rem, 2.5vw, 1.08rem) / 1.35`, chống tràn 2 dòng vụng về trên màn hình vừa và nhỏ.
  - Action buttons `.consent__acts button`: Chiều cao gọn `clamp(30px, 4vw, 34px)`, padding `0 clamp(12px, 3vw, 16px)`, khoảng cách nút `clamp(6px, 1.8vw, 8px)`.
  - Icon & Close button: Scale icon `.mobile-modal__icon` về `clamp(16px, 2.2vw, 18px)` và nút đóng `.mobile-modal__close` về `clamp(26px, 3.2vw, 28px)`.
  - Bump cache `mashloop-v57` trên `web/sw.js` và `?v=57` trên `web/index.html`. Đồng bộ Desktop, Mobile, Git và HF Space.
- **Thanh tăng giảm độ sáng ánh đèn (Room Light / Neon Glow Slider)**:
  - Thêm thanh trượt `#s-glow` (0% đến 200%, mặc định 100%) tại tab Cài đặt > Màu ("Ánh sáng của căn phòng").
  - Tích hợp hàm `theme.setGlow(level)` điều khiển trực tiếp biến CSS `--glow-mult`, khuếch đại hào quang `--glow`, độ rực màu `--fill-a`, và `theme.glowGain()` trong visualizer Canvas (bụi sáng, xung nhịp, dải spectrum, halo).
  - Phòng vệ an toàn với `typeof theme.setGlow === "function"` chống lỗi cache module.
- **Thêm 3 bộ màu mới (Theme Color Palettes)**:
  - **Cyberpunk**: Cyan điện quang kết hợp tím đêm Tokyo rực rỡ (`#00f0ff` & `#bd00ff`).
  - **Cực quang (Aurora)**: Xanh ngọc mint & lục bảo phương bắc huyền ảo (`#00e6a8` & `#10b981`).
  - **Hoàng hôn (Sunset)**: Vàng hoàng kim, cam san hô và tím chiều sâu lắng (`#f59e0b` & `#f43f5e`).
  - Nâng tổng số theme lên 6 bộ hoàn chỉnh: Theo mood, Neon, Cyberpunk, Cực quang, Hoàng hôn, Hổ phách.
- **Khắc phục lỗi CSS các khối màu swatch (`.swatch`)**:
  - Tách selector `.kind span` thành `.kind span:not(.swatch)` để không ghi đè layout `display: flex !important` của 3 chấm tròn màu `<i>` trong `.swatch`.
  - Khôi phục hình tròn 16px hoàn hảo với box-shadow viền nét.
- **Sửa lỗi lệch vị trí khối tab ([Thư viện] [Tinh chỉnh]) đè lên ô tìm kiếm trên Mobile**:
  - Gỡ bỏ thuộc tính lỗi `position: sticky; top: var(--topbar-h, 58px);` trên `.panel__head` ở breakpoint mobile (`max-width: 899px`).
  - Trả `.panel__head` về luồng tài liệu tự nhiên (`position: relative;`), chấm dứt triệt để hiện tượng header tab trôi lơ lửng và đè lên input tìm kiếm thư viện.
- **Khắc phục lỗi xén icon âm lượng trên Mobile**:
  - Bổ sung `padding: 0 8px 0 6px` và `margin-right: 2px` cho `.deck__vol` tại `@media (max-width: 520px)` và `@media (max-width: 370px)`.
  - Giữ khoảng cách an toàn 26px so với đường cong bán nguyệt của viền dock, ngăn chặn hoàn toàn việc sóng âm bị viền nét đứt cắt vào.
- **Căn thẳng hàng các thẻ theo cấp bậc (Icon, Tiêu đề, Mô tả)**:
  - Chuyển `.kind` từ CSS Grid không cố định hàng sang `display: flex; flex-direction: column; justify-content: flex-start; align-items: flex-start; gap: 8px;`.
  - Căn đồng mức pixel tuyệt đối theo chiều ngang cho toàn bộ thẻ trong mọi hàng: Cấp 1 (Icon/Swatch), Cấp 2 (Tiêu đề in đậm), Cấp 3 (Đoạn mô tả ngắn).
- **Thanh xử lý lỗi theo lô (Error Management Bar)**:
  - Thanh capsule phong cách ambient tinh tế `#lib-error-bar` với nút `Thử lại` và `Xoá`.
  - Tích hợp endpoint `/api/tracks/batch` hành động `"reanalyze"` xử lý hàng loạt bài hát lỗi trong 1 request.
- **Dọn dẹp note phím tắt và hoàn thiện Modal phím tắt (`?`)**:
  - Xóa bỏ đoạn text note phím tắt rườm rà dưới tab Cài đặt. Toàn bộ phím tắt được tập trung đầy đủ trong modal phím tắt (mở bằng icon `?` hoặc nhấn phím `?`).
- **Nâng cấp Động cơ chuyển bài (Transition Engine)**:
  - Chuyển bài cưỡng bức (Force Transition): Nhấn nút Next, phím `N` hoặc click trực tiếp vào nút giao hòa âm $\infty$ trên canvas.
  - Sidechain Vocal Ducking tự động hạ 3.5 dB mid band bài trước khi mix kiểu mashup/acapella.
  - Huy hiệu Camelot hòa âm (`keyA ⇄ keyB`) trực quan tại điểm giao nhau $\infty$.
  - 2 hiệu ứng chuyển bài DJ mới: Tape stop (`tape`) và Filter sweep (`sweeper`).
- **Khắc phục triệt để hiện tượng con trỏ phát sáng (Playhead) bị khựng / giật (Micro-stutter)**:
  - **Bù trễ lượng tử hóa đồng hồ âm thanh (Audio hardware buffer quantization)**: Web Audio `currentTime` cập nhật gián đoạn theo chunk buffer WASAPI/CoreAudio (~10–20ms/lần). Màn hình quét 60Hz (16.6ms) hay 120Hz/144Hz (8.3ms/6.9ms) đọc trùng giá trị cũ làm điểm sáng đứng khựng 1 frame rồi vọt tiếp. Khắc phục bằng bộ nội suy thời gian thực trôi pha mượt theo wall-clock `performance.now()` (`_smoothAudioT` với `drift * 0.15`), giữ chuyển động liên tục 144 FPS.
  - **Khử đông cứng ranh giới beat (Beat boundary freeze)**: Xóa bỏ việc clamp `frac` ở 1.0 theo `T.dur[e.beat]` lý tưởng. Thay bằng delta thời gian thực giữa 2 sự kiện nhịp liên tiếp trong timeline (`nextE.t - e.t`), đảm bảo chuyển động mượt 100% qua các khớp beat.
  - **Tối ưu hóa lượng giác Halo Spectrum bằng Lookup Table**: Precompute bảng `HALO_COS` & `HALO_SIN` (180 điểm), tính tọa độ vòng tròn qua công thức cộng góc $\cos(a_0 + \theta) = \cos a_0 \cos \theta - \sin a_0 \sin \theta$. Cắt giảm hoàn toàn 360 hàm `Math.cos/sin` mỗi frame và loại bỏ GC allocations qua mảng phẳng.
  - **Cache Version**: Bump cache `mashloop-v48` trên `web/sw.js` và `?v=48` trên `web/index.html`. Đồng bộ Desktop, Mobile và HF Space.
- **Độ nét Canvas toàn diện (Web, Desktop, Mobile)**:
  - **Windows Desktop DPI Awareness**: Thêm `SetProcessDpiAwarenessContext(-4)` (Per-Monitor DPI Aware V2) trong `loopbox/desktop.py` triệt tiêu hoàn toàn hiện tượng Windows DWM bitmap-scaling gây mờ pywebview khi màn hình đặt tỉ lệ 125%/150%.
  - **Khử răng cưa & mờ xoay Canvas (2x-4x SSAA)**:
    - `web/js/viz.js`: Supersample `_buildLayer` và `_idleLayer` (hình vô cực $\infty$) bằng canvas ngoài luồng độ phân giải cao `layerScale = Math.min(Math.max(round(dpr * 2), 2), 4)`. Khi xoay góc tùy ý (`_drawRing` / `_drawIdle`), thuật toán downsampling SSAA phần cứng giữ cho các nét hairline 1px, vạch chia dial, điểm hạt bụi (dust) và khối nhịp luôn sắc sảo tuyệt đối, không bị nhòe mờ.
    - Ép kích thước `S` (đường kính layer) luôn là số chẵn (`S % 2 === 0`), triệt tiêu độ lệch 0.5px subpixel gây nhòe nét.
    - Snapping tọa độ tâm `px, py` về lưới pixel vật lý (`Math.round(val * dpr) / dpr`).
    - Làm tròn kích thước layout `w, h` và gán trực tiếp `canvas.style.width = w + "px"`, `canvas.style.height = h + "px"`, chống GPU compositor làm mờ subpixel trên mobile flex/grid.
    - Cập nhật canvas mini track thumbnail thành 72x72px (tỉ lệ 2x nguyên vẹn với 36px CSS).
- **Sửa lỗi đè CSS làm hẹp Modal Playlist (#pl-modal) & Phím tắt (#shortcuts-modal)**:
  - Selector `.consent` ở cuối file CSS (`min(460px, ...)`) trước đó đã đè lên `.pl-modal` do cùng độ đặc hiệu và nằm sau, khiến width bị khóa ở 460px làm chữ "tại)." bị rớt dòng đơn độc.
  - Sửa thành `.consent.pl-modal, dialog.pl-modal, .pl-modal { width: min(530px, calc(100vw - 32px)) !important; }` và thêm `text-wrap: pretty;` cho `.pl-modal__hint`.
  - Mở rộng `.shortcuts-modal` lên `min(640px, calc(100vw - 32px)) !important;` và `text-wrap: pretty;` chống rớt từ "cuối." trong mẹo phím tắt.
- **Sửa lỗi nút Thêm Playlist không hiển thị modal**:
  - Khắc phục `ReferenceError: Cannot access 'onCancel' before initialization` (TDZ error) trong `showModal()` tại `web/js/main.js`.
- **Sửa viền kép / bóng đổ input focus**:
  - Chuẩn hóa CSS focus của input text thành viền sáng đơn sắc `oklch(var(--acc) / 0.85)` và bóng mờ nhẹ, triệt tiêu lỗi đè 3 viền dày của nút bấm.
- **Đồng bộ âm lượng Desktop với Windows & Tuyến tính hóa**:
  - Khắc phục lỗi suy hao bậc 2 ($V^2$): khi pywebview điều khiển Master Volume của Windows, Web Audio `master.gain` được giữ cố định ở `1.0` (hoặc `0` khi mute).
  - Tăng tần số đồng bộ lên 25Hz và ép đồng bộ tức thì lúc khởi động.
  - Loại bỏ keydown intercept phím âm lượng phần cứng trên bàn phím.
- **Nâng trần Dung lượng & Thời lượng Nhạc**:
  - `MAX_UPLOAD_MB`: Tăng từ 80 MB lên **500 MB** (hỗ trợ file WAV/FLAC, file nén zip nhiều bài đến 2 GB).
  - `MAX_DURATION_S`: Tăng từ 15 phút (900s) lên **60 phút** (3600s, 1 tiếng trọn vẹn).
- **Cập nhật định danh ứng dụng di động (appId)**:
  - Đổi toàn bộ `com.truclv.mashloop` thành `com.m3ik18dp.mashloop` trên `capacitor.config.json`, Gradle `build.gradle`, Android Java package (`com/m3ik18dp/mashloop/MainActivity.java`), XML strings, iOS Xcode project (`project.pbxproj`) và test suite `tools/test_onnx_and_mobile.py`.
- **Service Worker & Cache**:
  - Cập nhật cache version `mashloop-v45` trong `web/sw.js` và `?v=45` trong `web/index.html`.


## Mục tiêu Hoàn thành
- **Rà soát & Vá lỗ hổng**:
  - `Range: bytes=start-end`: Đã thêm hàm clamp `start = max(0, start)` chống crash `OSError` khi client gửi range âm (`loopbox/server.py`).
  - `select_folder()`: Chuyển sang `os.walk(onerror=...)` chống crash `PermissionError` khi người dùng chọn ổ đĩa có thư mục hệ thống khóa quyền (`loopbox/desktop.py`).
- **Task 1.1 - 1.3 (Core Backend & Streaming)**: Chunked streaming 64 KiB, Range 206, Sparse link ranking, SQLite session persistence (`data/sessions.db`).
- **Task 2.1 - 2.4 (Frontend & Mobile Continuity)**: MediaSession API, silent background audio anchor, adaptive RAM memory eviction, latency compensation.
- **Task 3.1 - 3.2 (PWA & DSP)**: Service Worker, manifest.json, nhịp lẻ 3/4 & 6/8.
- **Task 4.1 (Desktop App)**:
  - Ứng dụng Desktop chạy native Microsoft Edge WebView2 qua `pywebview`, hộp thoại Native Windows File/Folder Dialog, endpoint `POST /api/desktop/ingest_local` nạp file trực tiếp từ đĩa NVMe.
  - Tùy biến thanh tiêu đề Windows 11 Dark Mode (`DWMWA_USE_IMMERSIVE_DARK_MODE` & `DWMWA_CAPTION_COLOR = 0x00100D0B`) tiệp màu chuẩn với giao diện dark ambient `#0b0d10`, chữ kem mềm `#e8e6e3`.
  - Khởi chạy không cần hiện màn hình đen cmd (`pythonw.exe` & `hide_console()`), tạo sẵn file nhấp đúp 1-click `run-desktop.bat` và `run-desktop.vbs`.
- **Task 4.2 (ONNX Model Pipeline)**:
  - Script xuất model `tools/export_onnx.py` xuất `Beat This!` sang `data/models/beat_this.onnx` (79.3 MB) với dynamic axes cho time frames.
  - Module `loopbox/analysis/onnx_tracker.py` chạy suy luận qua ONNX Runtime (CPU / DirectML / CUDA).
  - Tích hợp trong `loopbox/analysis/models.py`: tự động nạp ONNX tracker khi có model ONNX, giảm tiêu tốn VRAM/RAM so với PyTorch gốc, sai số max diff $< 10^{-5}$.
- **Task 4.3 (Mobile Capacitor Shell & Native Projects)**:
  - Cấu hình Tailscale IP `http://100.118.230.52:8765` vào `capacitor.config.json` và đồng bộ vào cả `android/` và `ios/`.
  - Mở rộng cấu hình server `loopbox/config.py` và `loopbox/server.py` để lắng nghe trên `0.0.0.0` (chấp nhận kết nối từ IP Tailscale của iPhone/Android).
  - Thêm nút "Cài Mobile" dạng pill trên thanh điều hướng đầu trang `web/index.html`.
  - Thiết kế modal ambient kính mờ `#mobile-modal` chứa mã QR SVG vector (`web/img/qr-tailscale.svg`) quét tức thì, cùng hướng dẫn cài đặt PWA và native chi tiết cho iOS (Safari Add to Home Screen) và Android (Chrome Install).
  - Tối ưu CSS Safe-Area (`env(safe-area-inset-top)`, `env(safe-area-inset-bottom)`) cho tai thỏ iPhone / Dynamic Island.
  - Chặn kéo nảy trang (`overscroll-behavior-y: none`) và xóa highlight tap mặc định (`-webkit-tap-highlight-color: transparent`).
  - Sinh hoàn chỉnh project native Android Studio tại thư mục [`android/`](file:///d:/JOB/DEV/MashLoop/android), bổ sung quyền chạy nền `WAKE_LOCK`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK` trong `AndroidManifest.xml`.
  - Sinh hoàn chỉnh project native Xcode tại thư mục [`ios/`](file:///d:/JOB/DEV/MashLoop/ios), bổ sung capability `UIBackgroundModes: audio` trong `Info.plist`.
  - Đồng bộ web assets và cấu hình qua `npx cap sync` (Exit Code 0).

- **Desktop Icon & Universal Ambient Modal**:
  - Tạo bộ icon đa độ phân giải `web/img/icon.ico` (16x16 đến 256x256) từ logo vô cực `web/img/favicon.svg`.
  - Tích hợp icon chính thức vào `loopbox/desktop.py` cho cả thanh tiêu đề (`WM_SETICON`) và Taskbar qua CLR `window.native.Icon = Icon(...)`.
  - Xóa bỏ hoàn toàn `alert()` và `confirm()` trắng của trình duyệt; thay bằng modal ambient `<dialog id="app-modal" class="consent modal-dialog">` với backdrop blur, hiệu ứng động, và nút xoá viền đỏ nổi bật.
  - Ghi đè `window.alert` sang hàm `showModal()` bất đồng bộ, bảo đảm không bao giờ hiện popup hệ thống.
- **CUDA OOM & Asyncio Socket Fixes**:
  - `loopbox/analysis/models.py`: Chuyển Demucs sang cơ chế streaming từng cửa sổ (giữ tensor trên CPU, chỉ gửi từng chunk 7.8s lên GPU), đỉnh VRAM giảm từ >4GB xuống ~1GB, tương thích hoàn toàn card 4GB GTX 1650 Ti.
  - Tắt `shifts=0` giúp tăng tốc độ tách beat x2 và giảm 50% RAM trung gian.
  - Bắt toàn diện `(OutOfMemoryError, RuntimeError)` tự động giải phóng VRAM và fallback an toàn sang CPU nếu thiếu tài nguyên.
  - `loopbox/__init__.py`: Bắt ngoại lệ socket Windows `WinError 10054` trong `_call_connection_lost` triệt tiêu log rác khi client ngắt luồng audio.
  - Re-build thành công `dist/MashLoop/MashLoop.exe` tích hợp toàn bộ bản vá.

- **Standalone EXE & Windows Installer Tooling**:
  - Tạo file đặc tả PyInstaller [`mashloop.spec`](file:///d:/JOB/DEV/MashLoop/mashloop.spec) gom runtime, model ONNX, assets `web/`, và icon app.
  - Tạo script 1-click [`build-exe.bat`](file:///d:/JOB/DEV/MashLoop/build-exe.bat) tự động cài đặt PyInstaller và đóng gói ra `dist\MashLoop\MashLoop.exe`.
  - Đã chạy build hoàn tất `dist\MashLoop\MashLoop.exe` (Exit Code 0), test khởi động độc lập không lỗi.
  - Đã tạo shortcut trên Desktop `MashLoop.lnk` qua [`tools/create_shortcut.ps1`](file:///d:/JOB/DEV/MashLoop/tools/create_shortcut.ps1).
  - Tạo file cấu hình Inno Setup [`installer.iss`](file:///d:/JOB/DEV/MashLoop/installer.iss) để đóng gói thành file cài đặt Windows chuyên nghiệp `MashLoop-Setup-v1.0.0.exe` (Start Menu, Desktop shortcut, Uninstaller).

- **Fix PyInstaller Relative Import**:
  - Tạo `mashloop_app.py` làm entry point sạch ở thư mục gốc, cập nhật `mashloop.spec`.
  - Bổ sung fallback try/except import tuyệt đối trong `loopbox/desktop.py`.
  - Re-build `dist/MashLoop/MashLoop.exe` (Exit Code 0), chạy native không lỗi.

- **Mobile Safe-Area Topbar & Bottom Overlap Fix**:
  - Khắc phục lỗi media query (<= 899px) ghi đè `padding: 0 var(--space-4)` làm mất `env(safe-area-inset-top)` khiến thanh tiêu đề đè vào đồng hồ và pin iPhone.
  - Cập nhật `.topbar` với `padding-top: max(calc(env(safe-area-inset-top, 0px) + 8px), 12px)` và `height: calc(var(--topbar-h) + max(env(safe-area-inset-top, 0px) + 8px, 12px))`.
  - Thêm `padding-bottom: max(env(safe-area-inset-bottom, 0px), var(--space-4))` cho `.panel` tránh thanh Home Indicator iOS đè chữ.

- **Fork Git Repository & Clean Ignore**:
  - Thiết lập `.gitignore` chuẩn hóa chống đưa thư mục build (`dist/`, `build/`), cache di động (`.gradle/`, `Pods/`), `node_modules/`, logs vào git.
  - Đổi remote gốc thành `upstream` (`https://github.com/lvt1693/mashloop.git`).
  - Thêm remote `origin` trỏ về fork của người dùng: `https://github.com/m3iK18dp/mashloop.git`.
  - Cập nhật `README.md` với bảng ghi nhận công trạng chi tiết tác giả gốc Truc (`@lvt1693`), trang chủ gốc `mashloop.truclv.com`, và tác giả fork Phạm Doãn Kiếm (`@m3iK18dp`).
  - Đã đẩy toàn bộ nhánh `main` lên GitHub fork `origin/main` thành công (Exit Code 0).

- **Eliminate Cross-Platform Auto-Resume Bug & SW Cache Invalidation**:
  - Xóa bỏ triệt để event listener `document.addEventListener("visibilitychange", ...)` trong `web/js/engine.js`: Event này trước đó tự gọi `ctx.resume()` mỗi khi cửa sổ bị ẩn/thu nhỏ/chuyển màn hình, gây ra lỗi tự phát lại trên MỌI nền tảng (Desktop, Web, Mobile).
  - Tách bạch logic nút `#btn-play`: Chỉ kích hoạt `unlockAudio()` khi bắt đầu bài hát mới, không kích hoạt khi bấm Tạm dừng.
  - Nâng cấp `web/sw.js` lên version `mashloop-v5` với chiến lược **Network-First**: Tự động xóa sạch cache cũ và luôn tải code JS/CSS mới nhất từ máy chủ, tránh tình trạng điện thoại dùng lại file script cũ.
  - Đồng bộ tài nguyên sang native Capacitor và cập nhật vào `dist/MashLoop/_internal/web`.

- **Fix Windows SMTC Pause Bouncing & Web Audio Clock Re-Anchor**:
  - Khắc phục lỗi nút Pause trên Windows SMTC bị nảy lại Play: Cập nhật `playbackState` đồng bộ ngay đầu handler, loại bỏ hoàn toàn `ensureActive()` tự động hồi sinh `_bgAudio` trong lúc beat scheduler đang chạy.
  - Khắc phục lỗi bấm Play thanh thời gian chạy nhưng không có tiếng: 
    - Loại bỏ `fadeMaster` làm kẹt `master.gain` ở mức câm `0.0001` (-80dB) do xung đột giữa `linearRampToValueAtTime` và `setTargetAtTime`. Chuyển `engine.setVolume` sang `cancelScheduledValues + setValueAtTime` an toàn tuyệt đối.
    - Chặn `_tick()` khi `userPaused === true` tránh trôi thời gian ngầm.
    - Tái neo `this.nextTime = now + 0.08` và khởi tạo lại voice ngay tại beat hiện tại khi bấm Tiếp tục/Play, giải quyết dứt điểm hiện tượng 64 beat bị bỏ qua vào khoảng không.
    - Cập nhật Service Worker lên `mashloop-v8`.

- **Mobile Retina Display Sharpness Optimization**:
  - Nâng giới hạn DPR từ 2 lên 3 (`Math.min(window.devicePixelRatio || 1, 3)`): Màn hình iPhone Retina (DPR 3.0) trước đó bị giới hạn ở 2.0x khiến GPU phải upscale thêm 1.5x làm mờ nét vẽ.
  - Bổ sung `this.dpr` vào cache key của `ring.layerKey`: Ngăn chặn việc tái sử dụng buffer độ phân giải thấp khi xoay màn hình hoặc thay đổi viewport.
  - Siết chặt ngưỡng tái dựng layer `layerR` từ 15% xuống 3%: Giữ tỉ lệ vẽ luôn xấp xỉ 1:1, loại bỏ hiện tượng nội suy bitmap làm mờ các sợi dây nối beat (jump chords) và dial ticks.
  - Kích hoạt `imageSmoothingQuality = "high"` cho cả main canvas và offscreen layer canvases.
  - Nâng cấp Service Worker lên `mashloop-v9`.

- **Mobile Lock Screen Keep-Alive & Auto-Expire Cleanup**:
  - Thiết lập cơ chế Keep-Alive đệm 3 phút cho silent audio anchor khi bấm Tạm dừng: Ngăn chặn iOS đóng băng tiến trình WebKit và tự động suspend WebAudio context khi màn hình khoá một lúc.
  - Tự động hủy box control sau 3 phút không thao tác (`playbackState = "none"`, `metadata = null`) để tiết kiệm pin và dọn sạch màn hình khoá.
  - Bấm Dừng hẳn (Stop) sẽ dọn sạch box control ngay lập tức.
  - Nâng cấp Service Worker lên `mashloop-v10`.

- **Sleep Timer, The Deck Controls & Shortcuts Modal (Commit `72288ed` & `977699d`)**:
  - Hẹn giờ tắt (Sleep Timer): tự ngưng phát sau 15, 30, 45, 60 phút hoặc hết bài (`setSleepTimer`, `clearSleepTimer`), smart fade dịu âm lượng trong 8 giây cuối bằng Web Audio `fadeVolume(0, 8)`, hiển thị countdown real-time trên Deck.
  - The Deck: Thêm nút Khóa bài (`#btn-lock`, phím `L`), Tắt tiếng (`#btn-mute`, phím `M`), Lọc âm đêm (`#btn-night`, Night Warmth EQ shelf filter at 4.5 kHz, phím `E`).
  - Phím tắt & Trợ giúp: Thay thế text hint cũ trên topbar bằng nút `#btn-shortcuts-modal` mở hộp thoại `<dialog id="shortcuts-modal">` kính mờ, liệt kê đầy đủ phím tắt và mẹo thao tác canvas.
  - Fix duplicated icons trên Deck bằng CSS `!important` display toggles cho trạng thái lock/mute.
  - Fix `PermissionError [WinError 5] Access is denied` và `[Errno 13]` trên Windows bằng 8 vòng retry backoff exponential + direct write fallback trong `loopbox/library.py` và `loopbox/analysis/pipeline.py`.

- **Hugging Face Spaces ZeroGPU & Static Route Serving (Commit `aa940a4`)**:
  - Khắc phục màn hình đen tĩnh (blank black screen) trên Space: Gradio 6 `demo.launch()` tạo mới `server_app` nên các route mount trước `launch()` bị xóa. Di chuyển `_mount_mashloop(demo.server_app)` xuống sau `demo.launch(prevent_thread_lock=True)` để đảm bảo `/web/`, `/css/`, `/js/`, `/img/`, `/audio/` và các API endpoints (`/api/...`) luôn trả về HTTP 200.
  - Thêm thẻ `<script>` trong `head` tự động chuyển hướng các lượt truy cập trực tiếp từ top window vào `/web/` full-screen mượt mà.
  - Vá lỗi Python 3.12 `BaseSelectorEventLoop._close_self_pipe` `ValueError: Invalid file descriptor: -1`.
  - Khởi động worker ở module level bảo đảm xử lý bài hát và dọn dẹp bộ nhớ trên Space.
  - Đã upload và trigger build tự động trên Space `m3ik18dp/MashLoop` (`0d5132c`).

- **Dynamic QR Code & Mobile Modal Adaptation (Commit `9365041`)**:
  - Tự động nhận diện host: `#mobile-modal` tự cập nhật URL hiển thị theo môi trường (`https://m3ik18dp-mashloop.hf.space` trên Space, `http://100.118.230.52:8765` trên Tailscale, `http://localhost:8765` trên máy local).
  - Endpoint `/api/qr` trong `loopbox/server.py`: Sinh mã QR SVG vector thời gian thực bằng thư viện `qrcode`, trả về HTTP 200 kèm cache 24h.
  - Cập nhật footer disclaimer trong `web/index.html` làm rõ bản quyền phi thương mại và ghi nhận đóng góp fork.
  - Cập nhật `README.md` và `installer.iss` với link Space và đề xuất mô tả GitHub About.
  - Nâng cấp Service Worker lên `mashloop-v12`.

- **3-Band Studio EQ Suite & Presets Popover (Commit `6d2c4ac`)**:
  - Nâng cấp Web Audio Engine (`web/js/engine.js`) với chuỗi 3 bộ lọc biquad độc lập: Low-Shelf 100Hz, Peaking 1.8kHz, High-Shelf 4.5kHz (`eqLow`, `eqMid`, `eqHigh`).
  - 5 preset chất lượng phòng thu: Chuẩn/Gốc (`flat`), Âm đêm dịu (`night`), Bass Boost (`bass`), Tôn giọng (`vocal`), Lofi Chill (`lofi`).
  - Popover chọn EQ `#eq-popover` kính mờ OKLCH dynamic lighting, nút `#btn-eq`, badge trạng thái `#eq-badge`.
  - Phím tắt <kbd>E</kbd> tuần hoàn nhanh 5 preset: `flat` -> `night` -> `bass` -> `vocal` -> `lofi` -> `flat`.

- **Live DJ Telemetry & Camelot Key Badge**:
  - Hiển thị Camelot Key (`.badge-camelot`), Tông gốc, và BPM thời gian thực ngay trên góc trên bên phải `#ro-tr` bên cạnh thời lượng lặp, số lần nhảy beat và chuyển bài.

- **Multi-Source Internet Ingestion & Batch Album/Playlist Importer (Commit `785e36a`)**:
  - Hỗ trợ nạp nhạc từ 16+ nền tảng internet: YouTube, SoundCloud, Spotify, Zing MP3, Bandcamp, TikTok, Facebook, Instagram, Twitter/X, Bilibili, Vimeo, Dailymotion, Audius, Mixcloud, Jamendo và Web Audio trực tiếp.
  - Nhận diện và bóc tách tự động Album/Playlist: Hỗ trợ YouTube Playlist (`/playlist?list=...` & `watch?v=...&list=PL/OLAK`), Spotify Album & Playlist (`open.spotify.com/album/` & `/playlist/`), SoundCloud Sets/Albums, Zing MP3 Album/Playlist, Bandcamp Album, v.v.
  - Spotify Smart Metadata Engine: Trích xuất danh sách bài hát từ `__NEXT_DATA__` embed không cần API key, tự động tìm kiếm đối sánh song song qua `ThreadPoolExecutor` trên YouTube để lấy audio chất lượng cao.
  - Bảo mật SSRF: Chặn toàn bộ IP loopback và dải IP mạng nội bộ (`127.0.0.1`, `localhost`, `10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`, `169.254.169.254`).
  - Nâng cấp `MAX_PLAYLIST` lên 50 bài và nới rate limit `new_track` lên 60.
  - Giao diện: Cập nhật hint/placeholder và thông báo tiến độ nạp album thời gian thực. Bumper Service Worker lên `mashloop-v14`.

- **Unlink Fork & Chuyển Repo sang Private**:
  - Do cơ chế GitHub chặn trực tiếp đổi visibility của public fork sang private ("Public forks can't be made private"), quy trình đã thực hiện:
    1. Đổi tên fork cũ thành `m3iK18dp/mashloop-fork-archive`.
    2. Tạo mới repository độc lập `m3iK18dp/mashloop` với thuộc tính `private = True`, `fork = False`.
    3. Đẩy toàn bộ commit history và nhánh `main` lên repository private mới.
    4. Xóa remote `upstream` trên local git để tách biệt hoàn toàn khỏi mạng lưới repo gốc.
  - Kiểm tra trạng thái GitHub API: `m3iK18dp/mashloop` đạt chuẩn `private: True`, `fork: False`.

- **Tối ưu Responsive Control Deck trên Mobile (Commit `692f8a9`)**:
  - Khắc phục lỗi thanh điều khiển `.deck` tràn màn hình điện thoại do thanh trượt volume và các nút mở rộng:
    1. Giới hạn `.deck`: `max-width: calc(100vw - 16px)`, `box-sizing: border-box`, `border-radius: 9999px`.
    2. Trên màn hình di động ($\le 520\text{px}$): Ẩn thanh trượt volume dài (`input[type="range"]`) và nhãn số `em` gây tràn (người dùng điện thoại chỉnh âm lượng bằng phím cứng hoặc trong tab Tinh chỉnh), giữ lại nút Quick Mute `.btn-mute` 36px gọn gàng.
    3. Thu nhỏ nút Play trung tâm xuống 48px, các nút chức năng xuống 36px-40px với `gap: 3px`, bảo đảm 7 nút điều khiển vừa khít và cách mép màn hình thoải mái trên mọi iPhone/Android (từ 320px đến 430px).
    4. Điều chỉnh popover Hẹn giờ và EQ neo vào lề phải không bị tràn biên.
    5. Nâng cấp Service Worker lên `mashloop-v15`.

- **Playlist Management & Auto-Ingest (Commits `77c45b3`, `b382c2a`)**:
  - Đưa nút `[+ Playlist]` lên chung hàng với `lib-count` ở góc phải `.shelf-head`.
  - Tự động nạp bài hát qua URL, search, hoặc tải file/zip vào playlist đang kích hoạt (`addTracksToActivePlaylist`).
  - Sửa bug hiển thị chuỗi phát nhạc: đếm chính xác số bài đang bật (`enabled !== false`) trên tổng số bài ready (khi bỏ 1 bài hiện đúng `27/28`).
  - Đồng bộ âm lượng 2 chiều giữa web/app và OS Master Volume: Windows Desktop (`WindowsVolume` COM Core Audio), Android native (`AndroidAudio` & `VOLUME_CHANGED_ACTION`), web shortcuts (`[` / `]` và phím âm lượng đa phương tiện).
  - Chuẩn hóa toàn bộ hệ thống biểu tượng bằng Vector SVG sắc nét (0% emoji nhựa):
    - Đặt độ mờ `opacity: 0.42` cho các nút thao tác bài hát (`play`, `playlist`, `toggle chain`, `delete`) ở trạng thái chờ (thay vì ẩn hoàn toàn 0% opacity), khi rê chuột sáng 100%.
    - Bổ sung SVG icon danh sách playlist cho nút `btn-create-pl`, chip "Tất cả", nút "Tạo & thêm" trong modal, icon bóng đèn cho mẹo nghe nhạc, và icon lấp lánh vector cho chân trang.
    - Nâng cấp Service Worker lên `mashloop-v21`.

- **Vá lỗi YouTube Mix / Radio Playlist & Auto-Healing Session (Commit `4cb4eae`, Space `dc467cc`)**:
  - Khắc phục lỗi `could not resolve: Failed to extract any player response` trên YouTube:
    - Bổ sung cấu hình `extractor_args.youtube.player_client: ["android", "ios", "mweb", "web", "tv"]` trong `loopbox/download.py` để bypass triệt để cơ chế chặn IP datacenter của YouTube trên Hugging Face ZeroGPU.
    - Nhận diện toàn diện các định dạng playlist YouTube kể cả YouTube Mix / Radio (`list=RD...`, `list=PL...`, `list=OLAK...`), làm sạch query rác (`&t=...`, `&start_radio=...`).
    - Bổ sung cơ chế fallback tự động: nếu tải dạng playlist không được thì tự động bóc tách video đơn lẻ theo `watch?v=`.
    - Kiểm thử thực tế trên Space sống: Nạp thành công trọn vẹn 50 bài hát từ playlist `https://www.youtube.com/watch?v=LsqqAiPzE3s&list=RDLsqqAiPzE3s&start_radio=1&t=353s`.
  - Khắc phục lỗi "Mất kết nối tới server":
    - Thêm endpoint `@app.get("/api/health")` kiểm tra liveness.
    - Cải tiến cơ chế auto-healing trong `web/js/api.js` và `web/js/main.js`: khi server khởi động lại hoặc session hết hạn (410), client tự động reset `session.id = null` và xin cấp session mới ngay lập tức thay vì bị kẹt cứng ở thông báo lỗi.
    - Nâng cấp Service Worker lên `mashloop-v22`.

- **Dynamic Multi-Level SVG Volume Icons & System Volume Sync (Commit `b5dd7b0`, Space `bd6c2c4`)**:
  - Biểu tượng âm lượng vector SVG đa cấp độ không dùng icon nhựa/emoji:
    - 4 trạng thái SVG hiển thị theo mức âm lượng thực tế:
      - `mute`: Loa kèm dấu chéo đỏ (`#f87171`) khi âm lượng = 0 hoặc bấm tắt tiếng.
      - `low`: Loa 1 sóng âm khi âm lượng $1\% - 33\%$.
      - `med`: Loa 2 sóng âm khi âm lượng $34\% - 66\%$.
      - `high`: Loa 3 sóng âm khi âm lượng $67\% - 100\%$.
    - Hàm `updateVolumeIcon(vol, muted)` cập nhật tức thì `data-level` và tooltip tiếng Việt (`Bật tiếng (M)` / `Âm lượng X% (M: Tắt)`).
  - Làm rõ cơ chế đồng bộ âm lượng hệ thống:
    - **Web Browser (Chrome/Edge/Safari/Firefox)**: Bị giới hạn bởi Sandbox bảo mật chuẩn W3C, trình duyệt cấm tuyệt đối web script can thiệp/lắng nghe Master OS Volume để chống trang web độc hại phá hoại thính giác hoặc phần cứng loa. Bổ sung bắt phím phần cứng `AudioVolumeUp`, `AudioVolumeDown`, `AudioVolumeMute` ưu tiên cấp cao nhất trên trang web.
    - **Desktop App (`MashLoop Desktop`)**: Đồng bộ 2 chiều 100% thời gian thực với Windows Master Volume qua Windows Core Audio COM API (`IAudioEndpointVolume`).
    - **Mobile App (Android APK)**: Đồng bộ qua Android Native Bridge (`AudioManager`).
  - Nâng cấp Service Worker lên `mashloop-v23`.

- **Fix Mobile Input Zoom, Error Layout Break & YT Bot Fallback (Commit `e3a97d2`, Space `f0f004a`)**:
  - Khắc phục lỗi chữ báo lỗi dài gây vỡ/tràn giao diện:
    - Bổ sung `word-break: break-word`, `overflow-wrap: anywhere`, `max-width: 100%` cho `.results:not(:empty)`, `.results .msg`, `.msg`.
    - Tạo hàm `clean_error()` trên backend (`loopbox/download.py`, `loopbox/server.py`) và `cleanUiError()` trên frontend (`web/js/main.js`): Lọc bỏ toàn bộ terminal spam, đường link wiki yt-dlp, cờ `--cookies`, trả về câu thông báo ngắn gọn, dễ hiểu (`YouTube yêu cầu xác minh bot hoặc video bị giới hạn...`, `Video này không khả dụng hoặc đã bị tác giả xóa...`).
    - Tạo kiểu dáng hộp lỗi `.msg.msg--err` viền đỏ êm mắt.
  - Khắc phục lỗi Safari tự phóng to giao diện (zoom) khi chạm vào ô nhập liệu:
    - Chuẩn hóa `font-size: 16px !important;` cho toàn bộ input văn bản (`.add__field input`, `.pl-modal__create input`, `.modal-input`). Safari iOS chỉ tự động zoom khi font-size $< 16\text{px}$.
    - Bổ sung `maximum-scale=1` vào `<meta name="viewport">` trong `web/index.html`.
  - Hỗ trợ dán trực tiếp link chia sẻ Playlist MashLoop:
    - Nhận diện tham số `pl_tracks=` / `tracks=` khi người dùng dán link chia sẻ vào ô "Thêm bài vào thư viện", tự động nạp thẳng playlist và kích hoạt mà không chuyển sang `yt-dlp`.
- **Fix YouTube Mix / Radio Unviewable Error (Commit `46ef1e5`, Space `d75f20d`)**:
  - Khắc phục lỗi `YouTube said: This playlist type is unviewable`:
    - Nguyên nhân: Các danh sách Mix/Radio của YouTube có ID bắt đầu bằng `RD...` (như `RDOZYOyuLU5pg`), YouTube cấm xem trực tiếp dưới dạng trang playlist tĩnh `/playlist?list=RD...`. Danh sách Mix bắt buộc phải đi kèm với video gốc dạng `/watch?v=<vid>&list=RD<vid>`.
    - Xử lý: Tự động trích xuất mã video hạt giống (seed video ID) từ chuỗi ID danh sách phát (`RD<vid>`, `RDMM<vid>`, `RDAMVM<vid>`) trong `clean_youtube_url()` và fallback của `resolve()`, tự động chuyển đổi sang URL `/watch?v=OZYOyuLU5pg&list=RDOZYOyuLU5pg`.
    - Đã kiểm thử trực tiếp: URL `https://youtube.com/playlist?list=RDOZYOyuLU5pg` nạp thành công trọn vẹn 50 bài hát mà không báo lỗi.
  - Nâng cấp Service Worker lên `mashloop-v26`.

- **Fix Space Worker Spawn Bootstrap Crash & Multiuser Playlist Auto-Restore (Commit `98fb4bc`, Space `def6374`)**:
  - **Nguyên nhân sự cố trên Space**:
    1. Khi deploy lên HF Space, container khởi động lại mất 30–60s gây HTTP 502/503 tạm thời. Giao diện báo cam: *"Đang kết nối lại server…"*. Cơ chế exponential backoff trước đó tăng chu kỳ poll lên tới 30 giây khiến thông báo bị treo rất lâu ngay cả khi Space đã online.
    2. HF Space chạy chế độ `MULTIUSER = 1`. Khi container reboot, session RAM trên server bị reset (HTTP 410). `hooks.restore` cũ chỉ nạp lại bài từ `metas.map(m => m.id)` (vốn đã rỗng), nên không nạp lại các bài hát nằm trong Playlist được lưu tại `localStorage` của trình duyệt. Dẫn tới chip hiển thị `Album (42 bài) (0)` và thư viện trống.
    3. Trong `app.py`, hàm `_ensure_worker()` bị gọi tại phạm vi module cấp cao (module level). Khi `worker.start()` spawn tiến trình con qua `ProcessPoolExecutor(..., mp_context=spawn)`, tiến trình con nạp lại `app.py` và kích hoạt lỗi `RuntimeError: An attempt has been made to start a new process before the current process has finished its bootstrapping phase`, làm chết pool phân tích.
  - **Giải pháp**:
    1. `app.py`: Dời việc khởi động worker ra khỏi module level; đặt vào hook `@fastapi_app.on_event("startup")` và khối `if __name__ == "__main__":` kèm `multiprocessing.freeze_support()`, chặn tiến trình con chạy đè `_ensure_worker()`.
    2. `web/js/main.js`: Cập nhật `hooks.restore` tự động thu thập bài hát từ cả `metas` và tất cả `playlists.flatMap(p => p.trackIds)` để khôi phục phiên nghe tức thì khi server khởi động lại.
    3. `web/js/main.js`: Bổ sung cơ chế auto-restore trong `ready().then(...)` cho chế độ `session.multiuser`, đưa chu kỳ poll khi mất kết nối về 2.5 giây thay vì trễ 30 giây.
    4. Nâng cấp Service Worker lên `mashloop-v27`.

- **Batch Track Management - Quản lý bài hát theo lô (Commit `d3be697`, Space `1ffd3c6`)**:
  - **Tính năng**:
    - Nút toggle `"Chọn"` / `"Xong"` tại header thư viện (`#btn-batch-toggle`) kích hoạt chế độ chọn nhiều bài hát.
    - Thanh điều khiển theo lô (`#batch-bar`):
      - Checkbox `"Tất cả"` chọn/bỏ chọn toàn bộ bài hát đang hiển thị.
      - Bộ đếm số lượng bài đã chọn (`#batch-count`).
      - Nút `"Vào chuỗi"`: Bật hàng loạt bài hát đã chọn vào chuỗi phát vô hạn (`enabled: true`).
      - Nút `"Bỏ chuỗi"`: Tắt hàng loạt bài hát đã chọn khỏi chuỗi phát (`enabled: false`).
      - Nút `"+ Playlist"`: Thêm hàng loạt bài đã chọn vào Playlist hiện có hoặc tạo Playlist mới.
      - Nút `"Xoá"`: Xoá hàng loạt bài hát đã chọn với modal cảnh báo an toàn.
      - Nút `"Xong"` / `✕`: Đóng nhanh chế độ chọn lô.
    - Checkbox trên từng hàng bài hát: Tự động đổi màu nền khi được chọn, bấm bất kỳ đâu trên hàng để toggle chọn/bỏ chọn.
    - Endpoint backend nguyên tử `POST /api/tracks/batch` (`loopbox/server.py`) và các hàm `set_enabled_many`, `remove_many` (`loopbox/sessions.py`) xử lý toàn bộ danh sách trong 1 request duy nhất (< 50ms), chống nghẽn mạng và rate-limit.
    - Nâng cấp Service Worker lên `mashloop-v28`.

- **Playlist Track Move, Copy, Reorder & Remove (Commit `14c9a09`, Space `a94b5ea`)**:
  - **Tính năng**:
    - **Sao chép / Di chuyển bài hát vào Playlist (`#pl-modal`)**:
      - Phân tách 2 chế độ rõ ràng qua thanh chuyển đổi trạng thái:
        - `[ Sao chép sang ]`: Giữ bài ở playlist hiện tại, nhân bản vào playlist đích.
        - `[ Di chuyển sang ]`: Thêm bài vào playlist đích, đồng thời tự động rút khỏi playlist hiện tại (khi đang duyệt một playlist cụ thể).
      - Hỗ trợ thao tác cho cả bài đơn lẻ và chọn nhiều bài theo lô (Batch mode).
      - Tạo playlist mới trực tiếp từ modal cũng hỗ trợ chuyển / sao chép tương ứng.
    - **Sắp xếp thứ tự bài hát trong Playlist (Reorder `▲` / `▼`)**:
      - Hiển thị 2 nút mũi tên lên `▲` và xuống `▼` trực tiếp trên từng hàng bài hát khi duyệt playlist.
      - Hoán đổi vị trí nguyên tử trong mảng `pl.trackIds`, lưu ngay vào `localStorage` và cập nhật giao diện không cần reload.
      - Chuẩn hóa hàm `filterMetas` và `renderLibrary` để hiển thị bài hát theo đúng thứ tự mảng playlist (từ bài 1 đến bài cuối).
    - **Bỏ bài hát khỏi Playlist (`pl-remove`)**:
      - Khi duyệt playlist cụ thể, nút xoá đỏ nguy hiểm được thay thế bằng nút `"Bỏ khỏi playlist này"` (biểu tượng dấu trừ). Thao tác này chỉ gỡ bài khỏi danh sách phát mà không xóa file gốc trên server / ổ đĩa.
      - Thanh công cụ chọn nhiều (`#batch-bar`) tự động hiện thêm nút `"Bỏ playlist"` khi đang ở chế độ duyệt playlist.
    - Nâng cấp Service Worker lên `mashloop-v29`.

- **Live Search, Smart Sorting, Queue Next Track, MP3 Download & Track Inspector (Commit `sw-v30`)**:
  - **Tính năng**:
    1. **Tìm kiếm & Lọc thời gian thực (`#lib-search-input`)**:
       - Tìm nhanh theo tên bài, nghệ sĩ (chuẩn hóa tiếng Việt không dấu qua `cleanVi`).
       - Lọc theo số BPM (sai số +-3 BPM) hoặc theo cung hòa âm Camelot Key (ví dụ `8A`, `11B`).
       - Nút xóa bộ lọc nhanh (`#lib-search-clear` & `#btn-clear-search-empty`).
    2. **Sắp xếp Thư viện Thông minh (`#lib-sort-select`)**:
       - Mới nhất (mặc định), BPM tăng dần (Chậm -> Nhanh), BPM giảm dần (Nhanh -> Chậm).
       - Cung hòa âm Camelot Key (vòng tròn 1A-12B cho DJ mix hài âm).
       - Tên bài hát (A -> Z), Thời lượng (Dài -> Ngắn).
    3. **Chỉ định Bài hát phát tiếp theo (Queue Next Track `targetNextId`)**:
       - Nút chuyển tiếp trên từng hàng (`queue-next` icon).
       - Badge `[Kế tiếp]` hiển thị cạnh tên bài hát.
       - Thuật toán `_planExit(t)` trong `Player` tự động ưu tiên tìm điểm chuyển nhịp / hòa âm mượt nhất sang bài đã chọn thay vì nhảy ngẫu nhiên.
    4. **Tải file âm thanh về máy (Direct Client-Side MP3 Download)**:
       - Tải trực tiếp file `.mp3` chất lượng cao từ bộ nhớ giải mã client qua `api.audio(id)`.
       - Hoạt động 100% offline/client-side, không cần gọi API render lại từ server, tương thích cả local và Space.
    5. **Xem chi tiết & Điểm nối hòa âm (Track Inspector Modal `#inspect-modal`)**:
       - Xem BPM, Camelot Key, Thời lượng, Số điểm nhảy vô tận.
       - Tải động danh sách các điểm nối (`/api/tracks/${id}/transitions`) sang các bài khác trong thư viện kèm kiểu nối (blend, drop, riser, wash...) và % độ mượt.
       - Nút xem bài liên kết, nút Phát ngay, Phát tiếp theo, và Tải MP3 trực tiếp từ modal.
    6. Nâng cấp Service Worker lên `mashloop-v30`.

- **Ambient Instrument UI Polish & Track Row Layout Fix (Commit `sw-v31`)**:
  - **Sự cố**: Hàng bài hát (`.track`) bị nhồi nhét tới 7–9 nút bấm (`acts`) rộng tới 250px khiến cột tiêu đề và nghệ sĩ bị bóp nghẹt chỉ còn 30px, dẫn tới chữ bị cắt cụt thành `"S.."`, `"C.."`, `"H.."`. Ô tìm kiếm (`.lib-search`) bị dropdown sắp xếp chiếm nửa thanh điều khiển, placeholder bị cắt thành `"Lọc n"` và đè lên nút xoá `(x)`.
  - **Khắc phục theo chuẩn Ambient Instrument UI**:
    1. **Tối ưu thanh công cụ (`.lib-tools`)**:
       - Cố định kích thước dropdown sắp xếp `#lib-sort-select` ở 104px với nhãn chữ ngắn gọn: `"Mới nhất"`, `"BPM ↑"`, `"BPM ↓"`, `"Key Camelot"`, `"Tên A-Z"`, `"Thời lượng"`.
       - Mở rộng vùng nhập liệu tìm kiếm lên > 230px, placeholder `"Lọc tên, BPM, Key..."` hiển thị trọn vẹn, không đè nút xoá.
    2. **Thu gọn hàng bài hát (`.track .acts`)**:
       - Giảm kích thước nút bấm từ 34px xuống 28px tactile chuẩn.
       - Loại bỏ các nút phụ trùng lặp khỏi hàng (`download`, `playlist`); giữ 4 nút thao tác nhanh: `queue-next` (chuyển tiếp), `play` (phát), `toggle` (vào/bỏ chuỗi), và `inspect` (chi tiết & tùy chọn).
       - Thêm `min-width: 0; overflow: hidden;` cho thẻ bao văn bản bài hát; giải phóng hơn 150px chiều rộng cho tiêu đề và nghệ sĩ hiển thị đầy đủ, không bị cắt cụt.
       - Ẩn nút xoá trực tiếp trên màn hình cảm ứng điện thoại (`@media (hover: none)`) để chống bấm nhầm; nút xoá hiển thị an toàn trên desktop khi rê chuột (`hover: hover`).
    3. **Nâng cấp Modal Chi tiết (`#inspect-modal`)**:
       - Bổ sung trọn bộ nút hành động 1-chạm: `"Phát ngay"`, `"Phát tiếp theo"`, `"Tải MP3"`, `"Playlist"`, `"Xoá bài"`.
- **Ambient Custom Popover, Batch-Bar Grid & Focus Bracket Fix (Awaiting User Review)**:
  - **Sự cố khắc phục**:
    1. **Nút modal Chi tiết (`#inspect-modal`) bị đè**: Nút `.inspect-acts` flex-wrap làm icon SVG phình to đè lên text, chữ bị tràn ra ngoài.
    2. **Viền focus ngoặc đơn cam `( (i) )`**: Nút `(i)` và các nút trên hàng `.track .acts` bị hiệu ứng focus-visible 4px cong 2 mép tạo thành hình ngoặc đơn méo mó.
    3. **Dropdown sắp xếp bật menu trắng Windows**: Thẻ `<select id="lib-sort-select">` kích hoạt popup native của Windows OS làm phá vỡ giao diện ambient dark chamber.
    4. **Thanh chọn theo lô (`#batch-bar`) bị wrap 3 dòng**: Nút chọn nhiều, đếm số lượng và các nút hành động bị wrap lộn xộn thành 3 dòng.
    5. **Hàng bài hát chật hẹp**: Panel desktop chỉ 392px, hàng bài hát có nút xoá chiếm chỗ làm tên bài bị cắt ngắn.
  - **Giải pháp xử lý**:
    1. **Custom Popover `#lib-sort-popover`**: Thay thế select native bằng popover kính mờ ambient (`oklch(0.20 var(--gc) var(--gh) / 0.96)`, blur 20px, border `oklch(var(--acc) / 0.35)`). Giữ hidden select cho test suite và trợ năng.
    2. **Cấu trúc lại `#batch-bar` 2 tầng**: Tầng trên `.batch-bar__head` (Tất cả + đếm số lượng + nút Xong); tầng dưới `.batch-bar__actions` chia lưới đều 4 cột (`grid-template-columns: repeat(4, 1fr)`) cho Chuỗi, Playlist, Tải MP3, Xoá.
    3. **Chia lưới 2 cột cho `#inspect-modal`**: `.inspect-acts` chuyển sang grid 2 cột (`repeat(2, 1fr)`), nút "Phát ngay" full width cột trên cùng. Cố định kích thước SVG `15px x 15px`, `white-space: nowrap`, loại bỏ hoàn toàn hiện tượng icon đè chữ.
    4. **Loại bỏ focus bracket**: Thêm rule riêng `.track .acts button:focus-visible` với `box-shadow: 0 0 0 1.5px var(--accent); border-radius: 6px`, không còn ngoặc cam `( (i) )`.
    6. **Triệt tiêu toàn diện border active/focus rác trên track acts**: Gán `outline: none !important; box-shadow: none !important; border: 0 !important;` cho `.track .acts button` trong mọi trạng thái (`:focus`, `:focus-visible`, `:active`), đồng thời gọi `actEl?.blur()` khi bấm và đóng modal để triệt tiêu mọi vệt outline/ngoặc đơn méo mó.
    7. **Thêm padding cho thanh Tab điều khiển (`.panel__head`)**: Bọc `.seg.tabs` vào container `.panel__head` với padding 16px đều 4 phía, ngăn chặn hoàn toàn việc nội dung thẻ con bị cắt ngang sát đáy nút tab khi cuộn.
    8. **Tái thiết kế ô nhập liệu (`.add__field`) chuẩn `ambient-instrument-ui`**:
       - Vỏ container kính mờ OKLCH (`oklch(0.18 ... / 0.85)`), bo góc 12px, bóng chìm `inset 0 1px 2px rgba(0,0,0,0.35)`.
       - Khi focus: Viền phát sáng amber dịu mắt (`oklch(var(--acc) / 0.85)` + glow `18px`), triệt tiêu hoàn toàn viền chữ nhật thừa bên trong input con.
       - Nút "Tìm" tactile bo góc 9px với hiệu ứng hover amber neon.
    9. **Tối ưu bộ công cụ lọc & sắp xếp (`.lib-tools`)**:
       - Đồng bộ chiều cao chuẩn 36px cho cả ô lọc (`.lib-search input`) và nút sắp xếp (`.lib-sort-btn`).
       - Ô tìm kiếm kính mờ bo góc 10px, icon kính lúp phát sáng amber khi focus.
       - Nút sắp xếp mở popover kính mờ 24px blur, tùy chọn hòa âm DJ / Camelot / BPM sắc nét.
    10. Nâng cấp Service Worker lên `mashloop-v35` kèm cache-busting `?v=35` trên `index.html`.

## Lệnh Kiểm tra đã Chạy & Exit Code
- `.venv\Scripts\python.exe tests\test_server_and_features.py` -> Exit Code 0 (`ALL TESTS PASSED WITH EXIT CODE 0`)
- `.venv\Scripts\python.exe tools/test_onnx_and_mobile.py` -> Exit Code 0 (`ALL T4.2 & T4.3 VERIFICATION TESTS PASSED`)
- `.venv\Scripts\pyinstaller.exe --noconfirm mashloop.spec` -> Exit Code 0 (Đóng gói hoàn tất `dist\MashLoop\MashLoop.exe`, 62.7 MB)
- `npx cap sync` -> Exit Code 0 (Đồng bộ tài nguyên web sang Android & iOS targets)
- `.venv\Scripts\python.exe tools/upload_to_space.py` -> Exit Code 0 (Deploy HF Space: commit `7ecb87f` trên `m3ik18dp/MashLoop`)
- `git push origin main` -> Exit Code 0 (Push GitHub: commit `126f62d` trên `m3iK18dp/mashloop`)

## Các phần còn tồn đọng và cảnh báo kỹ thuật
- Toàn bộ các nền tảng (Desktop EXE, Web, Mobile Capacitor, HF Space) đã được re-build và đồng bộ bản mới nhất.
- Đã loại bỏ dòng thống kê "X bài hát" thừa dưới tiêu đề playlist/album.
- Đã triệt tiêu viền chữ nhật focus của ô `#add-input`.
- Đổi appId sang `com.m3ik18dp.mashloop` hoàn tất đồng bộ trên Gradle, Java MainActivity, strings.xml, Xcode pbxproj, capacitor.config.json.
