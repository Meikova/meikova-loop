# PROJECT SESSION HANDOFF LOG

## Project Status
- Path: D:\JOB\DEV\MashLoop\
- Setup Mode: Upgrade, Desktop Native Shell, ONNX Inference & Mobile Capacitor Shell
- Initialized with Antigravity Titan Standards.

## Last Updated
- Timestamp: 2026-10-17 22:05:00
- Exit Code: 0

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

## Lệnh Kiểm tra đã Chạy & Exit Code
- `.venv\Scripts\python.exe tests\test_server_and_features.py` -> Exit Code 0 (`ALL TESTS PASSED WITH EXIT CODE 0`)
- `.venv\Scripts\python.exe tools/upload_to_space.py` -> Exit Code 0 (commit `1ffd3c64` on `m3ik18dp/MashLoop`)
- GitHub commit `d3be697` pushed to `origin/main` (Exit Code 0).













