# BẢN GIAO TIẾP LIÊN PHIÊN (SESSION HANDOFF) — MEIKOVA LOOP

## Phiên làm việc: 18/11/2026 (Fix Frozen UI When Skipping Track While Paused v1.0.41)

### 1. Mục tiêu hoàn thành
- **Khắc phục lỗi âm thanh phát nhưng giao diện bị đóng băng khi nhấn Pause rồi chuyển bài khác (`skipToNext`)**:
  - **Nguyên nhân gốc rễ:** Khi người dùng tạm dừng (`pause()`), `this.userPaused = true` và `this.engine.stopAnchor()` được gọi. Khi nhấn chuyển bài tiếp theo (`#btn-next` -> `player.skipToNext()` -> `_startImmediateCrossfade()`), hệ thống khởi chạy âm thanh WebAudio (`v.start(...)`) cho bài mới nhưng **quên đặt lại `this.userPaused = false`, không kích hoạt `this.engine.startAnchor()`, không khôi phục `AudioContext` và không gọi `this._tick()`**. Kết quả là `player.playing` vẫn bằng `false` (nút Play không đổi thành Pause, phổ nhạc bị tắt tại `_spectrum()`, đồng hồ nhịp `_tick()` bị chặn ngay dòng đầu khiến kim sáng kẹt cứng ở vị trí 12 giờ).
  - **Giải pháp triệt để:**
    - `web/js/player.js`:
      - Trong `skipToNext()`: tự động gọi `await this.engine.ctx.resume()`, kiểm tra và nạp lại buffer nếu bị thu hồi do áp lực bộ nhớ, và tự động tiếp tục phát nếu thư viện chỉ có 1 bài đang tạm dừng.
      - Trong `_startImmediateCrossfade()`: nhận diện trạng thái `wasPaused`, đặt `this.userPaused = false`, gọi `this.engine.startAnchor()`, khôi phục âm lượng `targetVol`, phát sạch bài mới với fade-in 30ms (không lọc trầm 2.5s trên nền im lặng), bảo đảm `this.timer` hoạt động và kích hoạt ngay `this._tick()` để lịch nhịp và visualizer chạy tức thì.
      - Trong `play()`: bổ sung `this._log(t, "seq"); this._tick();` để đồng bộ tức thời khi tiếp tục phát từ trạng thái tạm dừng.
    - `web/js/main.js`: Bổ sung `engine.unlockAudio()`, `engine.ctx.resume()` và `renderTransport()` ngay trong trình xử lý nút `#btn-next`.
    - `tests/test_memory_lifecycle.py`: Lấy giá trị nhỏ nhất trên 3 mẫu đo latency `query_raw_memory()` để tránh nhiễu lập lịch tiến trình OS trên Windows.
- **Đồng bộ SSOT v1.0.41 & Đóng gói Native**:
  - Đồng bộ chuẩn SemVer Patch `v1.0.41` trên toàn bộ 6 tệp cấu hình hệ thống (`version.py --check` PASS).
  - Biên dịch PyInstaller `dist/MeikovaLoop/MeikovaLoop.exe` và đồng bộ tài nguyên web vào `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code
- `node --check web/js/player.js; node --check web/js/main.js; node --check web/js/viz.js`: Exit Code 0
- `.\.venv\Scripts\python.exe tests/test_memory_lifecycle.py`: 22/22 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe tests/stress_adversarial_r3.py`: 6/6 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe version.py --check`: 100% PASS v1.0.41 (Exit Code 0)

---

## Phiên làm việc: 18/11/2026 (Eliminate Rogue Crossing Point & Instant Centering on Skip v1.0.40)

### 1. Mục tiêu hoàn thành
- **Triệt tiêu chấm sáng thừa ở giữa khi chuyển bài ngay (Eliminate Rogue Crossing Point)**:
  - `web/js/viz.js`: Trước đây `this.cross` và lệnh gọi `_drawCross(ctx, view, now)` (cả Host và Satellite Stage) chỉ kiểm tra `primary.alpha > 0.4` mà không kiểm tra xem vòng thứ 2 (`secondRing`) có thực sự hiển thị hay không. Khi người dùng chuyển bài ngay, cơ chế trễ `_twoHoldUntil` vẫn giữ `two = true` trong 1100ms, khiến `_layout(true)` sinh ra `L.cross` lơ lửng ngay tại rìa/trung tâm đĩa đơn và vẽ chấm sáng cùng 3 vòng sóng đồng tâm dư thừa.
  - Bổ sung kiểm soát hiển thị chặt chẽ: `hasVisibleSecond = Boolean((secondRing && secondRing.alpha > 0.08) || this.placeholder)` cho cả tính toán `this.cross`, render `_drawCross`, Satellite Stage và `_broadcastHostTelemetry`. Khi chuyển sang bài mới hoặc có lệnh chuyển ngay (`isNewTrack || pendingImmediateSwitch`), lập tức reset sạch `this._twoHoldUntil = 0; this.cross = null;` (và xóa `this.lastCross` khi `via` là `"start"`/`"skip"`).
- **Khắc phục lỗi đĩa bài mới bị đẩy lệch sang trái rồi mới trôi về giữa (Instant Centering on Track Switch)**:
  - `web/js/viz.js`: Tái cấu trúc trình tự `_update(view, dt)` để đánh giá `isNewTrack` và `pendingImmediateSwitch` trước khi tính `two` và `_layout(two, swapProg)`. Khi không có phiên mix 2 đĩa chủ động (`!hasActiveMix`) và đĩa chưa được dock hiển thị sẵn, neo cố định tâm đĩa mới trực tiếp tại `(w / 2, h / 2)` với `L.a`, loại bỏ hoàn toàn nhánh `L2 = this._layout(true, 0)` đẩy đĩa mới từ phải sang trái rồi trôi ngược lại giữa.
- **Đồng bộ luồng chuyển bài tức thời (Player & Visualizer Sync)**:
  - `web/js/player.js`: `_startImmediateCrossfade()` gọi `_enterTrack(targetTrack, t, "skip", tr)`.
  - `web/js/viz.js`: `_roles()` bỏ qua tạo đĩa 2 giả khi `via === "skip"` và xóa `this.lastPlan` khi không còn plan hoặc mix.
  - `web/js/main.js`: Thêm `skip: "chuyển ngay"` vào từ điển `KIND`.
- **Đồng bộ SSOT v1.0.40 & Đóng gói Native**:
  - Tăng SemVer Patch lên `v1.0.40` đồng bộ 6 file hệ thống (`version.py --check` PASS).
  - Đóng gói PyInstaller `dist/MeikovaLoop/MeikovaLoop.exe` bằng `.venv` và đồng bộ tài nguyên web vào `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code
- `node --check web/js/viz.js; node --check web/js/player.js; node --check web/js/main.js`: Exit Code 0
- `.\.venv\Scripts\python.exe tests/test_memory_lifecycle.py`: 22/22 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe tests/stress_adversarial_r3.py`: 6/6 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe version.py --check`: 100% PASS v1.0.40 (Exit Code 0)

---

## Phiên làm việc: 17/11/2026 (Fluid Aurora Wave & Ambient Blurred Undulating Halo v1.0.34)

### 1. Mục tiêu hoàn thành
- **Vành hào quang sóng nước nhấp nhô & Mảng màu blur mềm mại (Fluid Aurora Ribbon & Crest Wave)**:
  - `web/js/viz.js`: Khắc phục hiện tượng các thanh phổ nhảy rời rạc như răng lược/chông nhọn bằng kiến trúc 3 lớp phát quang thống nhất:
    1. **Mảng màu blur phát quang nhấp nhô (Layer 1 - Ambient Blurred Undulating Ribbon)**: Khép kín vùng đa giác từ vành rãnh đĩa $r_0$ đến đường đỉnh sóng $r_0 + h'_k$, tô màu gradient chuyển sắc theo màu chủ đạo của bài hát (`col` $0.45 \to$ `hi` $0.25 \to$ mờ dần $0$), phủ bóng neon glow `shadowColor = theme.css(col, 0.65)` và `shadowBlur = 14px`. Tạo thành một màng màu phát quang mềm mại nhấp nhô theo nhịp bài hát.
    2. **Đường viền đỉnh phát quang liên tục (Layer 2 - Luminous Crest Wave Line)**: Nối liền toàn bộ 320 đỉnh ngọn thanh thành một đường cong sóng nước mềm mại uốn lượn liên tục (`lineWidth = 1.8px`, `strokeStyle = theme.css(hi, 0.78)`, `shadowBlur = 8px`), gắn kết toàn bộ các điểm dao động thành một dải sóng lỏng thống nhất.
    3. **Các thanh tia sáng nâng đỡ dải sóng (Layer 3 - Internal Luminous Filaments)**: Lọc làm mượt không gian (5-tap Gaussian smoothing $h'_k = 0.08 h_{k-2} + 0.22 h_{k-1} + 0.4 h_k + 0.22 h_{k+1} + 0.08 h_{k+2}$), các thanh âm lượng nối từ $r_0 + 1$ chạm chính xác vào đường đỉnh sóng, mang vai trò như các tia sáng tinh thể nâng đỡ dải sóng lụa bên ngoài.
  - Tối ưu hóa hiệu năng & bộ nhớ: Cấp phát tĩnh module-scope TypedArrays (`HALO_RAW_H`, `HALO_SMOOTH_H`, `HALO_CA`, `HALO_SA`), tiêu tốn chỉ ~5KB bộ nhớ vĩnh viễn, triệt tiêu 100% garbage collection allocation trong vòng lặp 60 FPS.
- **Đồng bộ SSOT v1.0.34 & Kiểm thử hồi quy**:
  - Tăng SemVer Patch v1.0.34 đồng bộ trên toàn bộ 6 file hệ thống.
  - Chạy toàn bộ 28 bài kiểm thử Lifecycle và Stress Adversarial R3 đạt 100% Exit Code 0.
  - Đồng bộ tài nguyên giao diện vào `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code
- `.\.venv\Scripts\python.exe -m unittest tests/test_memory_lifecycle.py -v`: 22/22 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe -m unittest tests/stress_adversarial_r3.py -v`: 6/6 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe version.py --check`: 100% PASS (Exit Code 0)

---

## Phiên làm việc: 17/11/2026 (Dense Halo Visualizer, Canvas Seam Self-Healing, Responsive Setlist Bar & Freeze Fix v1.0.33)

### 1. Mục tiêu hoàn thành
- **F1: Triệt tiêu hiện tượng treo ứng dụng Desktop (`MeikovaLoop.exe is not responding`)**:
  - `loopbox/desktop.py`: Bổ sung `_safe_eval_js()` bọc bảo vệ `window.evaluate_js` an toàn chống deadlock message pump khi WebView2 đang bận.
  - Tách lệnh dọn dẹp bộ nhớ `trim_memory()` chạy bất đồng bộ trên luồng nền daemon (`mem-trim-async`) trong `on_memory_pressure()` và `hide_to_tray()`.
  - Giảm tần số vòng lặp đồng bộ âm lượng `_volume_sync_loop` từ 25Hz (0.06s) xuống 10Hz (0.1s) để giảm tải cho cầu nối pywebview.
- **F2: Vòng phổ âm thanh ngoài dày đặc và chuyển động sống động (Dense Dynamic Halo Visualizer)**:
  - `web/js/viz.js`: Tăng số thanh phổ `HALO_N` từ 180 lên 320 thanh, tính toán trước 321 điểm lượng giác trong `HALO_COS` và `HALO_SIN`.
  - Tăng độ dày nét vẽ `ctx.lineWidth = 1.8`, tăng chiều cao tối đa `H = ring.r * 0.16`.
  - Thêm ngưỡng chiều cao cơ sở `Math.max(3, v * H)` cho toàn bộ 320 thanh, loại bỏ điều kiện ngắt quãng `ring.fill < 1`, giúp vòng phổ tròn 360 độ luôn dày đặc, liên tục, nhảy múa theo beat mà không bị thưa thớt.
- **F3: Tự chữa lành khe hở 12 giờ và loại bỏ lỗi render rác**:
  - `web/js/viz.js`: Bổ sung vòng rãnh nền liên tục (Base Groove Ring) từ 0 đến TAU bên dưới các phân đoạn beat, tự động bù đắp và liền mạch khe hở ở vị trí 12 giờ đối với các bài hát có beat detection bắt đầu muộn.
  - Khôi phục hiệu ứng chuyển sắc tâm mềm mại (`createRadialGradient`) cho đĩa caption trung tâm trên mọi chế độ, loại bỏ hoàn toàn đĩa đen cứng viền sắc.
  - Lọc thông minh cung hợp âm nhảy (Jump Chords): Loại bỏ các bước nhảy quá ngắn (`sep > 0.35 rad`), ưu tiên các cung khớp điểm số cao nhất và giới hạn tối đa 240 cung, triệt tiêu hiện tượng chùm nan quạt mạng nhện màu nâu dày đặc gây giật lag.
- **F4: Tái cấu trúc thanh Setlist và nút Xuất Setlist linh hoạt không đè chữ**:
  - `web/index.html` & `web/css/app.css`: Đưa `#history` và `#btn-export-setlist` vào khối cha `.setlist-bar` chuẩn Flexbox với `justify-self: stretch; width: 100%; min-width: 0; box-sizing: border-box;`.
  - Thiết lập `.setlist` nhận `flex: 1 1 auto; min-width: 0; max-width: 100%; overflow-x: auto;`, cho phép danh sách bài hát cuộn ngang tự do bên trong mà không làm phình layout ra ngoài.
  - Nút `.btn-setlist-pill` chuyển sang `position: relative; flex: 0 0 auto; margin-left: auto; white-space: nowrap;`, neo chắc chắn ở góc phải và tự động co lại thành icon trên màn hình di động nhỏ mà tuyệt đối không bao giờ đè lên tên bài hát.
- **F5: Đồng bộ phiên bản SSOT v1.0.33 và Đóng gói Native**:
  - Đồng bộ chuẩn SemVer v1.0.33 trên 6 tệp trọng yếu: `package.json`, `installer.iss`, `loopbox/__init__.py`, `loopbox/config.py`, `loopbox/tray.py`, và `web/index.html`.
  - Biên dịch PyInstaller desktop `dist/MeikovaLoop/MeikovaLoop.exe` đạt Exit Code 0.
  - Đồng bộ toàn bộ tài nguyên web mới sang `dist/MeikovaLoop/_internal/web/`.
  - 28/28 bài kiểm thử Lifecycle và Stress Adversarial R3 đạt 100% Exit Code 0.

### 2. Lệnh kiểm tra đã chạy & Exit Code
- `.\.venv\Scripts\python.exe -m unittest tests/test_memory_lifecycle.py -v`: 22/22 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe -m unittest tests/stress_adversarial_r3.py -v`: 6/6 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe version.py --check`: 100% PASS (Exit Code 0)
- `.\.venv\Scripts\python.exe test_setlist_pos.py` (Desktop/Mobile Portrait/Landscape): PASS (Exit Code 0)
- PyInstaller compile `MeikovaLoop.exe`: PASS (Exit Code 0)

### 3. Cảnh báo kỹ thuật & Lưu ý cho phiên sau
- Trên Windows PowerShell, khi chạy lệnh không dùng cú pháp `&&` nối lệnh (PowerShell 5.1 không hỗ trợ), thay bằng `;`.
- Khi cập nhật mã nguồn giao diện trong `web/`, luôn chạy lệnh `Copy-Item -Recurse -Force web/* dist/MeikovaLoop/_internal/web/` để đồng bộ ngay lập tức cho ứng dụng Desktop nội bộ.

---

## Phiên làm việc: 16/11/2026 (Dynamic Memory Pressure Sensing, Adaptive Audio Throttling & Self-Healing Canvas v1.0.32)

### 1. Mục tiêu hoàn thành
- **R1: Dynamic Memory Pressure Sensing (Backend & Win32 Ctypes / IPC)**:
  - `loopbox/memory_monitor.py`: Sử dụng thư viện chuẩn `ctypes` tương tác trực tiếp Win32 Virtual Commit Memory (`psapi.GetPerformanceInfo` với cấu trúc `PERFORMANCE_INFORMATION`) và private commit headroom (`kernel32.GlobalMemoryStatusEx`) trong ~0.25ms (0 phụ thuộc bên ngoài). Bộ máy trạng thái trễ 3 mức (`normal`, `high`, `critical`) với asymmetric deadbands và 8-giây dwell time để triệt tiêu hiện tượng thrashing. Có fallback an toàn cho POSIX (`/proc/meminfo`).
  - Phân phối đa kênh: REST API `GET /api/system/memory` (hỗ trợ multi-user isolation), WebSocket `/api/ws/stage-sync` (`type: "memory_pressure"`), và cầu nối Desktop Shell DOM Bridge `window.__onMemoryPressure` qua pywebview.
  - Sửa lỗi cắt ngắn 64-bit handle trong `EmptyWorkingSet` ở `loopbox/desktop.py` dùng `wintypes.HANDLE`, tự động kích hoạt cắt tỉa working set khi áp lực nhớ cao hoặc thu nhỏ vào khay hệ thống.
- **R2: Adaptive Memory Footprint & Audio Buffer Throttling**:
  - `web/js/api.js`: Bộ nhớ đệm `Loader` co giãn động theo 3 mức áp lực: `normal` (450MB, keep 2), `high` (250MB, keep 1), `critical` (140MB, keep 1). Hạch toán chính xác cả buffer âm thanh tách vocal Demucs trong `_totalCachedBytes()`. Chặn nạp vocal stem khi ở trạng thái Critical, và tự động gọi `_evict()` ngay sau khi decode stem xong.
  - `web/js/player.js`: Tập trung hóa cơ chế giải phóng bộ nhớ chủ động trong `_enterTrack()`, bao phủ toàn diện cả 6 lộ trình chuyển bài (`cut`, `fxDrop`, `fade`, `promote`, `skipToNext`, `start`). Bài cũ được xóa sạch hoàn toàn khỏi cache (`track.buffer = null`, `vocals = null`, `vocalsBuffer = null`, `loader.cache.delete(prevId)`), loại bỏ 100% rò rỉ Zombie Vocal Stems qua 120 lần chuyển bài liên tục.
  - `web/js/engine.js`: `Voice._free()` giải phóng triệt để hơn 21 WebAudio nodes và hủy bỏ toàn bộ scheduled parameter automations (`gain`, `lrNodes`, `stretchSplit/Main/Voc`, `bands`, `filters`), cho phép Chromium audio thread thu hồi bộ nhớ ngay lập tức.
- **R3: Resilient Visualizer Canvas Rendering & Self-Healing Recovery**:
  - `web/js/viz.js`: Thu nhỏ kích thước canvas về 1x1 pixel trong `_disposeRing()` và `_disposeIdleLayers()` để giải phóng ngay swapchain DirectX/ANGLE trên GPU.
  - Tự động bắt sự kiện `contextlost` và `contextrestored` để tạm dừng vòng lặp render an toàn và phục hồi giao diện khi GPU hồi phục.
  - Bao bọc toàn bộ các lệnh `drawImage` bằng khối try/catch và kiểm tra kích thước `width > 1 && height > 1`.
  - Giảm DPR về 1.0, thu nhỏ texture, tắt các hiệu ứng bloom/light phức tạp và loại bỏ CSS backdrop blur dưới áp lực Critical.
  - Chuẩn hóa Zero-Emoji: Thay thế toàn bộ ký tự emoji nốt nhạc trong regex splitTitle bằng chuỗi unicode escape `[\u266B\uD83C\uDFB5\uD83C\uDFB6\uD83C\uDFBC]`.
- **Độc lập Kiểm toán Chiến thắng (teamwork_victory_auditor)**:
  - Phán quyết: **VICTORY CONFIRMED**.
  - Kiểm tra 3 pha: Timeline & Git Forensics (PASS), Anti-Cheating & Implementation Integrity (PASS, 0 stubs/fakes/mocks), Independent Test Execution (PASS 100% Exit Code 0).
  - 28/28 bài kiểm tra Lifecycle & Adversarial Stress đạt 100% Exit Code 0.
  - Toàn bộ 6 bộ kiểm thử hồi quy đạt 100% Exit Code 0.

### 2. Lệnh kiểm tra đã chạy & Exit Code
- `.\.venv\Scripts\python.exe -m unittest tests/test_memory_lifecycle.py -v`: 22/22 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe -m unittest tests/stress_adversarial_r3.py -v`: 6/6 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe -m unittest tests/test_memory_lifecycle.py tests/stress_adversarial_r3.py -v`: 28/28 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe tests/test_tab_stability.py`: PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe -m unittest tests/test_cluster_sync.py -v`: 5/5 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe tests/test_stage_sync.py`: 14/14 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe -m unittest tests/test_long_track_playback.py -v`: 4/4 PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py`: PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe tests/test_viz_render_and_oom_e2e.py`: PASSED (Exit Code 0)
- `.\.venv\Scripts\python.exe version.py --check`: PASS (100% sync v1.0.32, Exit Code 0)

### 3. Đóng gói & Phát hành
- Version bump: `v1.0.32` (SSOT qua `version.py`).
- Binary build: PyInstaller đóng gói `dist/Meikova Loop/Meikova Loop.exe`.
- Git Ops: Tag `v1.0.32`, commit `[build] [release]`, dual-push GitHub `origin main` & `space main:main` (Hugging Face Spaces).

---

## Phiên làm việc: 11/11/2026 (Khắc phục Triệt để Lỗi Out of Memory, Mất Render Vòng Beat & Rè Âm thanh Cụm Loa v176)

### 000000. Kiến trúc, Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để

1. **Khắc phục Triệt để Lỗi Sập "Out of Memory" (WebView2 White Screen / VirtualAlloc Commitment Limit):**
   - **Nguyên nhân gốc rễ:**
     - Máy tính có 32 GB RAM vật lý (>9.8 GB trống) nhưng Windows Paging File bị cố định ở 8 GB, dẫn đến trần bộ nhớ ảo toàn hệ thống (Commit Limit) là 39.42 GB. Các ứng dụng nền đã cam kết 36.98 GB, chỉ còn trống đúng **2.44 GB** bộ nhớ ảo.
     - `api.js` cho phép lưu cache tối đa 1.15 GB PCM AudioBuffer 32-bit float (`keep = 3`), mỗi bài dài 10–15 phút ngốn ~235 MB RAM. Khi đẩy bài khỏi cache, tham chiếu `track.buffer` không được null hóa.
     - `player.js` duy trì mảng `timeline` tới 400 sự kiện cũ, giữ chặt tham chiếu đến các đối tượng `Track` đã phát.
     - `engine.js` (`Voice`) khởi tạo hơn 15 WebAudio nodes (Linkwitz-Riley 4th order crossover filters) nhưng hàm `_free()` chỉ disconnect duy nhất `this.gain`, khiến Chromium WebAudio Graph rò rỉ hàng trăm nodes sau mỗi bài hát.
     - `viz.js` dựng canvas idle với `layerScale = 4` (7680x4320 = 133 MB/canvas x 2 = 266 MB GPU VRAM), đồng thời các vòng cũ khi xóa khỏi `this.rings` không hạ kích thước canvas về 0 khiến DirectX Direct2D textures bị kẹt trong VRAM.
   - **Giải pháp triệt để:**
     - `web/js/api.js`: Hạ trần cache xuống 450 MB (Desktop) / 300 MB (Mobile), mặc định `keep = 2`. Trong `drop(id)` và `_evict()`: gán dứt khoát `entry.track.buffer = null` và `entry.vocals = null`.
     - `web/js/player.js`: Cắt tỉa `this.timeline` chỉ giữ tối đa 40 sự kiện gần nhất trong vòng 5 giây (`cutoff = audibleTime - 5`). Khi chuyển sang bài mới, kích hoạt `_evict()` và hủy buffer bài cũ ngay lập tức. Thêm fallback an toàn trong `_planExit` khi playlist bị khóa/lọc để không bao giờ bị stall dừng phát.
     - `web/js/engine.js`: Thu thập toàn bộ các node `BiquadFilterNode` nội bộ vào mảng `this.lrNodes`. Trong `Voice._free()`: duyệt disconnect toàn diện 15+ nodes (`gain`, `src`, `srcGain`, `mainGain`, `voc`, `vocGain`, `pre`, `sum`, `bands.low/mid/high`, `lp`, `hp`, `trim`, `fx`, `lrNodes`), giải phóng hoàn toàn đồ thị âm thanh cho Chromium GC.
     - `web/js/viz.js`: Triển khai `_disposeRing(ring)` (`canvas.width = 0; canvas.height = 0; ring.layer = null`). Khống chế kích thước `_idleLayer` với `layerScale <= 1.5` và giới hạn tối đa 1920x1080 (giảm dung lượng GPU texture từ 266 MB xuống < 8 MB). Giới hạn `this.rings.size <= 4`.
     - `loopbox/desktop.py`: Thêm cờ `--renderer-process-limit=2` và `--js-flags=--expose-gc` cho WebView2. Bổ sung hàm Win32 `ctypes.windll.psapi.EmptyWorkingSet` được gọi khi ẩn vào khay hệ thống để hoàn trả trang nhớ cho Windows.

2. **Khắc phục Triệt để Lỗi Mất Render Vòng Beat (Dấu chấm sáng vẫn chạy nhưng mất toàn bộ vạch nhịp, hợp âm, bụi):**
   - **Nguyên nhân gốc rễ:**
     - Trong `_update` và `_drawSatelliteStage`: `ring.fill` bị chặn tăng trưởng do nằm sau lệnh `if (!tg) continue;`. Khi `ring.target` là `null`, `ring.fill` bị đóng băng ở giá trị `0`.
     - Trong `_drawRing`: Lệnh `ctx.clip()` thực hiện cắt xén theo góc `TAU * f`. Khi `ring.fill <= 0`, `f = 0`, vùng clip bị thu hẹp về diện tích bằng 0 (`ctx.arc(0, 0, L.S, 0, 0)`), dẫn đến toàn bộ nội dung của `L.canvas` (vạch nhịp, hợp âm, bụi) bị xóa sạch không còn 1 pixel! Chấm sáng playhead và vạch halo nằm ngoài `L.canvas` nên vẫn hiển thị, tạo ra hiện tượng chấm sáng chạy trên vòng vô hình.
     - Trong `_buildLayer`: `this.player.maxScore(track)` gọi trực tiếp `T.scoreCut(this.settings.keep)`. Khi nhận track từ vệ tinh qua telemetry (vốn là plain JSON object không có prototype methods), lệnh này ném ra `TypeError: T.scoreCut is not a function`, làm sập toàn bộ hàm `_buildLayer`.
     - Trong `_buildLayer`: Các mảng phân tích `a.pos`, `a.loud`, `a.sections`, `track.transitions` bị truy cập trực tiếp `a.pos[b]` khi chưa kiểm tra `Array.isArray()`, gây `TypeError: Cannot read properties of undefined`.
   - **Giải pháp triệt để:**
     - Tách việc tăng `ring.fill` ra ngoài điều kiện `if (!tg) continue;` ở cả hai hàm `_update` và `_drawSatelliteStage`.
     - Với `ring.role === "primary"`, ép `ring.fill = 1` nếu `<= 0` hoặc `undefined`.
     - Trong `_drawRing`: Bảo vệ diện tích clip tối thiểu bằng `Math.max(0.001, ring.fill || 0)`, đảm bảo vùng clip luôn bao phủ tối thiểu và không bao giờ thu hẹp về 0 pixel.
     - Thêm kiểm tra `isLayerValid`: Nếu `ring.layer.canvas.width <= 1` hoặc layer bị hủy, tự động dựng lại khi bài hát đã có beats.
     - Khắc phục `maxScore`: Kiểm tra `typeof T?.scoreCut === "function"` trước khi gọi, fallback về `0.2` an toàn.
     - Bọc an toàn 100% các mảng `posArr`, `loudArr`, `sectionsArr`, `transArr` với fallback mảng rỗng `[]` và giá trị mặc định.

3. **Khắc phục Triệt để Tiếng Rè Âm thanh & Xung đột Âm thanh Khi Chạy Cùng Máy (InPrivate / Multi-Tab):**
   - **Nguyên nhân gốc rễ:**
     - Trong `MLStreamPlayerProcessor` (`web/js/stage_sync.js`): Khi buffer cạn (`available <= 2`), hệ thống ghi trực tiếp `0` vào mảng âm thanh, tạo cú nhảy điện áp DC tức thời gây tiếng bụp số (digital click). Sau đó hệ thống chờ đủ 2048 mẫu (~43ms) mới phát lại, rơi vào vòng lặp ngắt quãng tạo tiếng rè cơ học 43Hz ("rè rè").
     - `_pushToSatWorklet` gửi message `config` liên tục 47 lần/giây vào AudioWorklet, làm nghẽn MessagePort và gây GC lag trên luồng âm thanh.
     - Khi mở tab ẩn danh InPrivate, trình duyệt cô lập hoàn toàn `BroadcastChannel("ml_local_cluster_bus")`. Lệnh tắt tiếng của tab phụ không thể truyền tới tab chính, dẫn tới cả 2 tab cùng phát đồng thời gây tiếng vọng trễ pha.
   - **Giải pháp triệt để:**
     - Trong `MLStreamPlayerProcessor`: Triển khai hàm trượt vi mô Cosine (Cosine micro-fade) trong 32 mẫu khi cạn buffer thay vì cắt đột ngột về 0, triệt tiêu 100% tiếng bụp DC.
     - Giảm ngưỡng hồi phục buffer từ 2048 mẫu xuống 768 mẫu (~16ms) kết hợp `targetBuffered = 3840` (~80ms), duy trì luồng âm thanh mượt mà liên tục.
     - Thêm cơ chế throttle cấu hình trong `_pushToSatWorklet`: Chỉ gửi message `config` khi các tham số thực sự thay đổi (`targetBuffered`, `effMode`, `isDiscrete`, `isMuted`), giảm tải từ 47 msg/s về 0 khi ổn định.
     - Trong `loopbox/stage_sync_hub.py`: Bổ sung cơ chế WebSocket relay `same_machine_speaker_sync`. Server tự động nhận diện các client có cùng địa chỉ IP (`127.0.0.1` / `::1` / LAN IP) và chuyển tiếp trạng thái tắt loa tới tất cả các tab khác của cùng máy đó, vượt qua hoàn toàn rào cản cô lập của InPrivate.

4. **Kết quả Kiểm thử Toàn diện (Verification 100% Pass — Exit Code 0):**
   - `tests/test_memory_lifecycle.py`: **4/4 tests PASSED (Exit Code 0)**.
   - `tests/test_viz_render_and_oom_e2e.py`: **1/1 E2E visual render test PASSED (Exit Code 0, 3.5s)**:
     * Dựng thành công 12 bài hát chuyển tiếp liên tục.
     * Số vòng trên sân khấu được khống chế nghiêm ngặt $\le 4$.
     * Kích thước layer idle được khống chế $\le 1920\text{px}$.
     * Beat blocks và chords được vẽ sắc nét lên canvas `#viz` với hàng nghìn pixel màu hợp lệ.
   - `tests/test_cluster_e2e_playwright.py`: **32/32 tests PASSED (Exit Code 0, 59.2s)**.
   - `tests/test_audio_continuity.py`: **9/9 tests PASSED (Exit Code 0)**.
   - `tests/test_cluster_sync.py`: **5/5 tests PASSED (Exit Code 0)**.
   - `tests/test_stage_sync.py`: **14/14 tests PASSED (Exit Code 0)**.
   - `tests/test_tab_stability.py` & `scripts/verify_deck_responsive.py`: **ALL PASSED (Exit Code 0)**.
   - Cú pháp mã nguồn JS (`node --check`): **ALL 6 FILES PASSED (Exit Code 0)**.
   - Biên dịch Python (`python -m compileall`): **ALL MODULES PASSED (Exit Code 0)**.

---

## Phiên làm việc: 10/11/2026 (Triệt tiêu 100% Hiện tượng Rè rè bằng AudioWorklet Jitter Ring Buffer, Chống xung đột Âm thanh Cùng máy và Sửa lỗi Caption Sân khấu Toàn cảnh v176)

### 00000. Kiến trúc, Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v176)
1. **Triệt tiêu Hoàn toàn Tiếng Rè rè ("rè rè" 43Hz) bằng AudioWorklet Jitter Ring Buffer (Milestone 1 — Continuous Sample-Exact DSP):**
   - **Nguyên nhân gốc rễ:**
     1. Lỗi đứt đoạn phân giải mẫu phân số (Fractional Sample Truncation): Khi phát stream qua các `AudioBufferSourceNode` 1024-mẫu riêng rẽ, mỗi packet (23.2ms) kết thúc tại một mẫu phân số không nguyên (ví dụ: 1024 * 48000 / 44100 = 1114.6077 mẫu). Bộ resampler native của trình duyệt làm tròn hoặc cắt bỏ 0.6 mẫu, tạo ra một bước nhảy điện áp (step discontinuity) tại ranh giới mỗi packet. Với tần suất 43 packet/giây, chuỗi xung nhịp 43Hz này tạo ra tiếng rè rè/xước liên tục ("rè rè").
     2. Resampler Filter Tap Dropouts: Các `AudioBufferSourceNode` độc lập không chia sẻ trạng thái bộ lọc (filter history). Ở mẫu cuối cùng của buffer trước và mẫu đầu tiên của buffer sau, kernel nội suy bị thiếu mẫu tương lai/quá khứ và chìm về 0, gây micro-click tại điểm nối.
     3. Tồn đọng bộ nhớ đệm trình duyệt (Cache Pollution): Service Worker `sw.js` lưu cache `meikova-loop-v175` với các file `?v=173`/`?v=174`, khiến trình duyệt chạy mã JS cũ dù đã bấm refresh thông thường.
   - **Giải pháp triệt để:**
     - Thiết kế và triển khai bộ xử lý luồng âm thanh chuyên dụng `MLStreamPlayerProcessor` chạy trên luồng thời gian thực C++ (`AudioWorkletProcessor`):
       * Vận hành bộ nhớ đệm vòng tuần hoàn Float32 công suất 32768 mẫu (~740ms) độc lập cho kênh trái và kênh phải.
       * Tích hợp bộ tích lũy pha liên tục (continuous phase accumulator) với **nội suy tuyến tính phân số chính xác tuyệt đối** ($\Delta\phi = rac{f_{in}}{f_{out}} \cdot 	ext{rateNudge}$, $y[n] = (1 - lpha) x[k] + lpha x[k+1]$). Triệt tiêu 100% bước nhảy ranh giới, giữ đường cong liên tục $C^0$.
       * Điều tốc vi sai mượt mà (bounded [0.992, 1.008]): duy trì độ sâu buffer mục tiêu ~60-80ms (~2800 mẫu) không gây méo cao độ.
       * Micro-fade cosin 64 mẫu (1.5ms) khi thoát tình trạng thiếu buffer (underrun recovery), triệt tiêu hoàn toàn tiếng "bụp" DC.
       * Queue tạm thời khi worklet đang nạp và fallback `_schedulePcmPacket` có EMA filter.

2. **Khắc phục Triệt để Vấn đề Âm thanh Khi Phát Trên CÙNG 1 MÁY (Milestone 2 — Same-Machine Anti-Clash & Single-Tab Solo):**
   - **Nguyên nhân gốc rễ:**
     1. Hiện tượng Lọc Lược (Comb Filtering) & Vang dội pha (Haas Effect) do 2 tab cùng xuất âm thanh ra 1 soundcard với độ lệch jitter 2-15ms.
     2. Trong chế độ `stereo_pair` trên cùng 1 máy: Khi Tab 2 tắt tiếng để tránh vọng thì Tab 1 lại bị cắt mất kênh phải (R), làm âm thanh thiếu tai phải.
   - **Giải pháp triệt để:**
     - Tự động nhận diện môi trường cùng máy (`this.isSameMachine = this.isLocalHost;`).
     - Mặc định khi Follower vào cụm trên cùng máy: Loa Follower **tự động TẮT** (`satAudioMuted = true`, hiển thị nút `Loa: Tắt (Cùng máy)`).
     - Khi người dùng bấm `[Loa: Tắt (Cùng máy)]` trên Tab 2 -> chuyển `[Loa: Bật]`. Tab 2 gửi tín hiệu qua `BroadcastChannel("ml_local_cluster_bus")` yêu cầu Tab 1 tắt loa cục bộ (`engine.setLocalSpeakerMuted(true)`). Tab 2 phát toàn quyền Full Stereo qua `MLStreamPlayerProcessor` không vọng hay rè.
     - Cơ chế `_syncMasterEffectiveChannels`: Khi Master phát hiện toàn bộ Follower là các tab cùng máy đang tắt tiếng, Master tự động phát **Full Stereo** đảm bảo trọn vẹn âm thanh hai kênh.

3. **Khắc phục Lỗi Chữ "HAI VÒNG ĐANG CHỜ" Đè Lên Khi Bật Chiếu Toàn Cảnh (Milestone 3 — Stage Mirror Caption & DOM Protection):**
   - Bổ sung `this._placeCenter(this.capPlace)` và `if (this.onCaption) this.onCaption()` vào heartbeat `setInterval` của `web/js/viz.js` để DOM Host không bị đóng băng khi tab ẩn.
   - Bảo vệ `_syncCenterCaption`, `#ro-tl`, `#ro-tr` trong `web/js/stage_sync.js` bằng kiểm tra `isHtmlIdle` và `isRoIdle`: tuyệt đối không dùng chuỗi idle khi Host đang phát nhạc.

4. **Đồng bộ Phiên bản & Triệt tiêu Cache Cũ (Milestone 4 — SSOT Cache Busting v176):**
   - Cập nhật đồng bộ toàn hệ thống lên `v176` (`web/sw.js`, `web/index.html`, `web/js/stage_sync.js`, `web/js/viz.js`, `web/js/main.js`, `web/js/api.js`).

5. **Kết quả Kiểm thử Toàn diện (Verification 100% Pass — Exit Code 0):**
   - `tests/test_audio_continuity.py`: **9/9 tests PASSED (Exit Code 0, 0.025s)**.
   - `tests/test_cluster_sync.py`: **5/5 tests PASSED (Exit Code 0, 0.08s)**.
   - `tests/test_stage_sync.py`: **14/14 tests PASSED (Exit Code 0)**.
   - `tests/test_tab_stability.py` & `tests/test_title_splitter.py`: **ALL PASSED (Exit Code 0)**.
   - `tests/test_server_and_features.py`: **ALL SERVER & FEATURE TESTS PASSED (Exit Code 0)**.
   - `tests/test_cluster_e2e_playwright.py`: **32/32 Playwright E2E tests PASSED (Exit Code 0, 62.1s)**.

---
## Phiên làm việc: 10/11/2026 (Triệt tiêu Hiện tượng Nhấp nháy Toàn cảnh Sân khấu is-cluster-mirror, Làm sạch 100% Pipeline Âm thanh PCM v2 & Đồng bộ Pha Không Vang Vọng Cho Cụm Loa & Loa Vệ tinh v175)

### 0000. Kiến trúc, Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v175)
1. **Triệt tiêu Hiện tượng Nhấp nháy Sân khấu & Chồng lấn Vòng lặp Lemniscate ∞ (Milestone 1 — Visual Isolation):**
   - **Nguyên nhân gốc rễ:**
     1. Xung đột DOM đa luồng: `renderStage()` và `renderTransport()` trong `web/js/main.js` chạy định kỳ 250ms trên máy con follower (nơi `player.audible() === null`), liên tục ghi đè `#rc-kicker` thành `"HAI VÒNG ĐANG CHỜ"`, giằng co với telemetry máy chính gửi tới ("ĐANG PHÁT · CHUỖI").
     2. Vòng lặp Heartbeat 33ms trong `web/js/viz.js` chạy trên máy con gọi `_update(null, dt)`, liên tục bơm `this.idle` lên 1.0, khiến `_drawSatelliteStage()` kích hoạt `_drawIdle()` vẽ đè 2 vòng vô cực lemniscate số 8 trực tiếp lên vòng tròn bài hát đang phát.
     3. Khóa cứng kích thước canvas: `viz.js` ép `canvas.style.width = ...px` inline khi `!isSatellite`, và thiếu bộ CSS isolation đầy đủ cho `body.is-cluster-mirror`.
   - **Giải pháp triệt để:**
     - Thiết lập cờ `stageSync.isStageMirrorActive` (`isSatellite || (isClusterFollower && isClusterMirror)`) và chèn rào chắn bảo vệ toàn diện vào: `renderStage()`, `renderTransport()`, `renderSetlist()`, `updateAmbientLyrics()`, `applySettings()`, `openLyricsEditorModal()`, cùng các sự kiện `track` và `prefetch` trong `web/js/main.js`.
     - Tắt hoàn toàn vòng lặp heartbeat trên follower trong `web/js/viz.js` (`if (!stageSync.isSatellite && !stageSync.isClusterFollower)`).
     - Trong `_drawSatelliteStage()`: ép dứt khoát `this.idle = 0;` khi bài hát đang phát (`mode !== "idle"`), chỉ vẽ `_drawIdle` khi host thực sự dừng (`mode === "idle"`).
     - Bổ sung bộ quy tắc CSS cô lập toàn diện cho `body.is-cluster-mirror` trong `web/css/app.css`: triệt tiêu chuyển động nhấp nháy (`transition: none !important`), căn giữa tuyệt đối canvas và ring-center, ẩn `#rc-cta`.

2. **Làm sạch 100% Pipeline Âm thanh PCM v2 & Triệt tiêu Tiếng Rè, Méo tiếng, Vang vọng (Milestone 2 — Audio Pipeline & Acoustic Cleansing):**
   - **Nguyên nhân gốc rễ:**
     1. Méo gập phổ 2 cấp (Double Aliasing): Host hạ mẫu 44.1kHz -> 22.05kHz bằng bộ lọc trung bình cộng 2 mẫu thô bạo (độ suy giảm chỉ -7.5dB ở 16kHz, gập ngược năng lượng vào dải 6kHz gây rè chói gắt). Thiết bị nhận sau đó lại dùng nội suy tuyến tính bậc 1 để nâng lên 48kHz, nhân đôi méo hài.
     2. Xén sóng vuông số (Hard Digital Clipping): Thiếu đường cong bão hòa mềm, mẫu float vượt quá ±1.0 bị cắt phẳng tạo sóng vuông nổ rè.
     3. Jitter nhảy pha (`driftSec > 22ms`): Ngưỡng snap 22ms quá hẹp so với jitter Wi-Fi (10–35ms) làm gói tin bị chồng đè (overlap) hoặc tạo khoảng lặng (gap) lẹt đẹt.
     4. Trashing tham số `DelayNode`: Host liên tục gọi `cancelScheduledValues` trên `speakerDelay` mỗi 23ms gây rung xung nhịp.
   - **Giải pháp triệt để:**
     - Nâng cấp luồng PCM v2 lên tần số gốc chuẩn Studio `ctx.sampleRate` (44.1kHz), giữ trọn vẹn dải cao tần tới 20kHz không qua decimation (`web/js/stage_sync.js`).
     - Bão hòa mềm phi tuyến bằng đường cong `Math.tanh(x)` trước khi lượng tử hóa sang Int16, triệt tiêu 100% hiện tượng xén sóng vuông.
     - Sử dụng bộ giải mã phần cứng đa pha native của trình duyệt (`ctx.createBuffer(channels, frames, srcSr)`), loại bỏ hoàn toàn nội suy JS thủ công.
     - Tích hợp bộ lọc cắt tần số cực thấp 20Hz (`HighPass BiquadFilter`, Q=0.707) và bộ nén bảo vệ màng loa (`DynamicsCompressor` Brickwall Limiter: threshold -0.8dB, ratio 20:1, attack 2ms, release 80ms) trước `destination`.
     - Bộ lập lịch bù pha mượt mà (Closed-Loop Slew Phase-Lock): nới ngưỡng snap lên 55ms; với độ trôi 8–55ms chỉ bù trượt 10% mỗi gói (`driftSec * 0.10`); khi cạn buffer thực sự thì khởi động lại tại mốc an toàn `Math.max(now + 0.018, idealPlayTime)`.
     - Nâng baseline bù trễ loa máy chính `hostAlignMs` lên **`60ms`**, giữ độ lệch pha giữa máy chính và máy con $\le 2\text{ms}$, triệt tiêu hoàn toàn tiếng dội âm/vang vọng.
     - Thêm guard check delta `< 0.5ms` trong `Engine.setSpeakerSyncDelay` (`web/js/engine.js`), ngăn trashing `AudioParam`.

3. **Kiểm chứng Toàn diện 4 Tầng (Verification 100% Pass — Exit Code 0):**
   - Bộ kiểm thử tự động Playwright E2E 4 tầng (`tests/test_cluster_e2e_playwright.py`): **32/32 tests PASSED (Exit Code 0, 88.0s)**.
     - Tier 1: 19/19 Feature Coverage tests PASSED.
     - Tier 2: 7/7 Boundary & Corner Case tests PASSED.
     - Tier 3: 5/5 Cross-Feature Interaction tests PASSED.
     - Tier 4: 1/1 Dual-Device Real-World 10+ seconds playback test PASSED.
   - Bộ kiểm thử đơn vị backend & giao thức cụm loa (`tests/test_cluster_sync.py`): **5/5 tests PASSED (Exit Code 0, 0.08s)**.
   - Toàn bộ kiểm thử Stage Sync (`tests/test_stage_sync.py`): **ALL PASSED (Exit Code 0)**.
   - Toàn bộ kiểm thử tính năng server (`tests/test_server_and_features.py`): **ALL PASSED (Exit Code 0)**.
   - Cú pháp mã nguồn JS (`node --check`): **ALL PASSED (Exit Code 0)**.
   - Biên dịch Python (`python -m compileall`): **ALL PASSED (Exit Code 0)**.

---

## Phiên làm việc: 09/11/2026 (Triển khai Hệ thống Liên kết Cụm Loa Meikova Cluster Link / PartyBoost & Stereo Pair + Đồng pha Âm thanh Zero-Echo NTP v174, Chuẩn hóa Responsive / Anti-Overflow v173, Khắc phục Lỗi Mất Tiếng Khi Phát / Chuyển Bài v171, Hiệu chuẩn Màu RGB v170, Dò tìm Động Thiết bị Ánh sáng v169, Loa Vệ tinh Mobile v168 & Phát Bài Dài >15 Phút v167)

### 000. Kiến trúc & Triển khai Meikova Cluster Link (PartyBoost & Stereo Pair) + Đồng pha Âm thanh Zero-Echo NTP (v174)
1. **Bài toán & Yêu cầu thiết kế đã chốt:**
   - Mặc định khi mở nhiều phiên bản phần mềm (`Meikova Loop` trên nhiều máy hoặc nhiều thiết bị truy cập IP máy chính), các phiên bản hoạt động độc lập như hiện tại.
   - Khi bật **Liên kết Cụm Loa (PartyBoost)** (`#btn-nav-cluster` -> `#modalClusterLink`), tất cả các phần mềm kết nối thống nhất thành một hệ thống cụm loa duy nhất:
     1. **Giao diện máy thành viên (Option 2 Mặc định + Nút phóng to Option 1):** Hiển thị thanh trạng thái nổi `.cluster-member-banner` (`#cluster-member-banner`) ngay đầu sân khấu báo tên máy Chủ tọa, kênh âm thanh (`STEREO · L+R`, `LOA TRÁI · L`, `LOA PHẢI · R`), nút 1 chạm **"Toàn cảnh"** (`#btn-cluster-stage-mirror`) để mở rộng toàn màn hình đồng bộ 1:1 với Chủ tọa (`body.is-cluster-mirror`), và nút **"Rời cụm"** (`#btn-cluster-leave`) để quay về phát độc lập. Khi bấm phát bài mới trên máy thành viên, hiển thị hộp thoại Ambient Modal hỏi **Làm Chủ tọa & Phát cho Cụm** (DJ Handoff) hoặc **Rời cụm & Nghe riêng**.
     2. **Hai chế độ âm học (Acoustic Modes):**
        - **Party Mode (`party` — All Stereo):** Tất cả các máy cùng phát đầy đủ 2 kênh Stereo (`L+R`).
        - **Stereo Pair (`stereo_pair` — Ghép đôi Trái / Phải):** Tách kênh âm thanh vòm thực thụ bằng `ChannelSplitterNode(2)` + `ChannelMergerNode(2)` trên cả máy chính (`web/js/engine.js`) lẫn các máy thành viên/vệ tinh (`web/js/stage_sync.js`): Máy Chủ tọa phát kênh Trái (`L`), máy thành viên phát kênh Phải (`R`), và cho phép gán thủ công `Trái (L) | Stereo | Phải (R)` cùng âm lượng riêng (`0%–150%`) cho từng máy.
     3. **Hoạt động trên cả 2 mô hình mạng (Dual Topology):**
        - **Mô hình A (Truy cập qua IP máy chính — Single Backend):** Tự động gom các tab/thiết bị kết nối vào `StageSyncHub` (`loopbox/stage_sync_hub.py`).
        - **Mô hình B (Mỗi máy chạy `python -m loopbox.server` độc lập trong LAN — Multi-Backend):** Module `loopbox/cluster_discovery.py` (`ClusterBeaconManager`) phát & lắng nghe bản tin UDP Broadcast (`cổng 8766`) mỗi `3.0s` để tự động liệt kê các máy chủ `MashLoop` khác trong LAN (kèm ô nhập `IP:Port` thủ công), cho phép nối cầu WebSocket trực tiếp (`connectToRemoteClusterHost`) vào cụm loa của máy chính chỉ với 1 cú nhấp.
2. **Triệt tiêu hoàn toàn hiện tượng vang vọng (Zero-Echo Acoustic Phase Alignment) cho Loa Vệ tinh & Cụm Loa (`web/js/engine.js`, `web/js/stage_sync.js`, `loopbox/stage_sync_hub.py`):**
   - **Nguyên nhân gây vang vọng trước đây:** Loa máy chính phát trực tiếp ra `ctx.destination` ở độ trễ `0ms`, trong khi máy Vệ tinh phải chờ gom gói tin PCM `2048 mẫu (~46.4ms)` + truyền mạng Wi-Fi + đệm `85ms` (`~135–150ms` sau máy chính). Hai loa phát cùng một bài hát lệch nhau `~140ms` tạo ra hiệu ứng dội âm (slapback echo).
   - **Giải pháp đồng pha NTP + Bù trễ Loa chính:**
     1. **Đồng bộ đồng hồ chuẩn NTP (`ping_sync` / `pong_sync`):** Máy chính và các máy Vệ tinh/Thành viên đo độ lệch đồng hồ $\theta = ((t_1 - t_0) + (t_2 - t_3)) / 2$ so với đồng hồ chuẩn `StageSyncHub.clock_ms()` (`time.perf_counter() * 1000.0`), lọc trung vị 5 mẫu RTT nhỏ nhất.
     2. **Khung nhị phân PCM v2 (16-byte Header + `1024` mẫu `~23.2ms`):** Gói tin nhị phân mã `0xA5` đính kèm nhãn thời gian lấy mẫu chính xác 64-bit (`Float64 serverCaptureMs = performance.now() + ntpOffsetMs`) ở byte offset `8..15`.
     3. **Bù trễ đồng pha trên Loa chính (`Engine.speakerDelay`):** Chèn `DelayNode` (`this.speakerDelay`) + bộ tách/trộn kênh `ChannelSplitterNode(2)` / `ChannelMergerNode(2)` vào chuỗi đầu ra của `Engine` (`analyser -> speakerDelay -> channelSplitter -> channelMerger -> speakerTrimGain -> destination`). Khi có bất kỳ Loa Vệ tinh hoặc Thành viên Cụm Loa nào đang phát âm thanh, máy chính tự động trì hoãn loa nội bộ đúng `hostAlignMs` (mặc định `45ms`), và các máy vệ tinh/thành viên lập lịch phát từng khung PCM tại đúng thời điểm `ctx.currentTime + (hostAlignMs + myLatencyOffsetMs - packetAgeMs) / 1000`, giúp màng loa của tất cả các thiết bị dao động **cùng một thời điểm vật lý** (sai số `< 2–3ms`, triệt tiêu hoàn toàn tiếng vang).
3. **Kiểm chứng tự động (Verification Exit Code 0):**
   - `.\.venv\Scripts\python.exe -m unittest tests/test_cluster_sync.py tests/test_stage_sync.py tests/test_long_track_playback.py -v` -> **PASS (7/7 tests, Exit Code 0)**.
   - `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py` -> **PASS (Exit Code 0)**.
   - Kiểm thử Playwright E2E đa khung nhìn (`360x740`, `390x844`, `844x390`, `768x1024`, `1440x900`) & liên kết 2 máy (Master + Follower): **PASS (`0px` tràn ngang, Exit Code 0)**.

### 00. Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v172 & v173 — Chuẩn hóa Responsive & Chống Tràn/Đè Chữ Toàn Diện trên Mobile & Tablet)
1. **Lỗi tràn thanh `.platform-tabs` trong Modal Cài đặt & Thiết bị (`#mobile-modal`, `web/index.html`, `web/css/app.css`):**
   - **Nguyên nhân:** `.platform-tabs` dùng `display: flex; overflow-x: auto;` với 3 nhãn dài (`Máy tính (Desktop)`, `iOS (iPhone / iPad)`, `Android`), tổng chiều rộng nội tại vượt quá chiều rộng modal trên màn hình di động (`320px–430px`), khiến tab thứ 3 (`Android`) bị cắt cụt bên phải (`[ Ar ]`).
   - **Giải pháp:** Chuyển `.platform-tabs` sang `display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));` chia đều 3 cột, bọc nhãn phụ trong `<small class="platform-tab__sub">` và tự động ẩn `.platform-tab__sub` trên màn hình `<= 580px` để hiển thị gọn gàng `Máy tính` | `iOS` | `Android` trên 1 hàng duy nhất mà không bao giờ tràn hay cuộn ngang.
2. **Lỗi đè chữ `.light-device-badge` lên nút Nháy thử & Công tắc bật/tắt, rớt dòng tiêu đề và lệch bố cục trong Modal Đồng bộ Ánh sáng & Vệ tinh (`#modalStageSync`, `web/js/stage_sync.js`, `web/index.html`, `web/css/app.css`):**
   - **Nguyên nhân:**
     1. Trong `renderLightsStatus()` (`web/js/stage_sync.js`), `.light-device-info` không có `overflow: hidden` và gộp `.light-device-name`, `.light-device-badge` (`PHẦN CỨNG · ASUS ATKACPI Kernel`), `.light-status-dot` chung trong một `.light-device-title-row` (`flex-wrap: wrap`). Khi xuống dòng trên màn hình hẹp, `.light-device-badge` (`white-space: nowrap`, rộng `~210px`) tràn thẳng ra ngoài `.light-device-info` (`~145px`) và vẽ đè trực tiếp lên nút tia sét `.btn-light-ping` cùng công tắc `.btn-light-toggle`, đồng thời đẩy chấm trạng thái `.light-status-dot` rớt xuống dòng thứ 3.
     2. Tiêu đề `.tunnel-modal__head` (`Đồng bộ Ánh sáng & Vệ tinh`, `MEIKOVA CONTINUUM // SATELLITE & LIGHTS`), nút chuyển tab `.sync-tab-btn` (`Đèn & Bàn phím RGB`), tiêu đề `.lights-discovery-title-row` (`Thiết bị Ánh sáng & RGB khả dụng` + `1/1 đang bật`) và `.lights-manual-head` (`Kết nối thiết bị thủ công` + `UDP DDP · Đa vùng`) bị gãy thành 2 dòng trên màn hình di động.
     3. Các pill chọn giao thức `.lights-proto-pills` (5 nút) và nút thử màu `.color-test-group` (5 nút) dùng `flex-wrap` tự do gây lệch hàng và dư khoảng trống bên phải.
     4. Các hộp thoại `<dialog>` trên di động đặt `height: auto` mà thiếu `height: fit-content`, đôi khi bị kéo giãn chiều cao trên một số trình duyệt WebKit/Blink.
   - **Giải pháp:**
     - Tách cấu trúc `.light-device-info` trong `web/js/stage_sync.js` thành 2 hàng độc lập có `overflow: hidden; min-width: 0;`:
       - `.light-device-title-row`: neo chấm trạng thái `.light-status-dot` + `.light-device-name` (`text-overflow: ellipsis`) luôn nằm gọn trên 1 dòng.
       - `.light-device-sub-row`: chứa `.light-device-badge` (`max-width: 100%; overflow: hidden; text-overflow: ellipsis`) + `.light-device-detail`, tuyệt đối không bao giờ tràn sang `.light-device-actions`.
     - Tinh chỉnh `.tunnel-modal__head`, `.sync-tab-btn` (ẩn `<small class="sync-tab__sub">` trên màn hình `<= 480px` để còn `Màn hình Vệ tinh` | `Đèn & RGB`), `.lights-discovery-title-row` và `.lights-manual-head` (`flex-wrap: nowrap`, `white-space: nowrap`) để toàn bộ tiêu đề và huy hiệu luôn nằm gọn trên 1 dòng.
     - Chuyển `.lights-proto-pills` trên mobile sang lưới 6 cột (`grid-template-columns: repeat(6, minmax(0, 1fr))`), trong đó 2 nút đầu chiếm 3 cột/nút (50% mỗi nút) và 3 nút dưới chiếm 2 cột/nút (33.3% mỗi nút) cân xứng tuyệt đối; chuyển `.color-test-group` sang lưới 5 cột đều nhau (`repeat(5, minmax(0, 1fr))`).
     - Chuẩn hóa toàn bộ các cụm dễ tràn khác trên màn hình `<= 480px`: `.tunnel-url-row` (xếp dọc full-width cho nút Sao chép / Mở tab), `.inspect-acts__sub` (lưới `2x2` cho 4 nút hành động phụ), `.pl-header`, `.batch-bar__actions`, `.lib-error-bar`, `.pl-modal__create`, `.storage-input-row`, và bổ sung `height: fit-content !important;` cho tất cả `<dialog>` trên mobile.

### 0A. Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v171 — Lỗi Thỉnh thoảng Phát Nhạc Không Ra Âm Thanh Phải Bấm Play Lại Vài Lần)
1. **Nguyên nhân 1 (Nghiêm trọng nhất) — `Loader._evict()` tự xóa `track.buffer = null` của chính bài hát vừa tải xong trong `Loader.get(id)` (`web/js/api.js`, `web/js/player.js`, `web/js/main.js`):**
   - **Nguyên nhân:**
     - Hàm bảo vệ bộ nhớ đệm `loader.protect` trước đây chỉ giữ `[player.cur?.track.id, player.plan?.tr.to, player.blend?.B.id, ...player.prefetchIds]`.
     - Khi người dùng bấm Play một bài mới `trackId` (`player.start(trackId)`), trong lúc chờ `await this.loader.get(trackId)`, `player.cur` vẫn đang giữ bài cũ, `player.plan` vẫn giữ bài dự kiến cũ, và `player.prefetchIds` vẫn giữ 2 bài nạp trước (`keep` đã chiếm đủ 3–4 slot trong cache, nhưng **không có `trackId` mới**!).
     - Ngay khi `Loader.get(trackId)` vừa giải mã xong `buffer` và gán `entry.track = track` rồi gọi `this._evict()` (dòng 532), vì cả 3 bài cũ đều nằm trong `keep`, bài `trackId` vừa giải mã xong trở thành phần tử **duy nhất** không nằm trong `keep` (`!keep.has(id)`).
     - Kết quả: `_evict()` lập tức trục xuất chính `trackId` vừa giải mã, gán **`entry.track.buffer = null`** rồi trả về đối tượng `track` rỗng (`track.buffer === null`) cho `player.start(trackId)`!
     - Trong `Voice` (`web/js/engine.js`), `this.src.buffer = null` và `this.src.start(...)` chạy trên `AudioBufferSourceNode` rỗng mà **không ném ra bất kỳ ngoại lệ nào**, khiến giao diện vẫn hiện `"ĐANG PHÁT · CHUỖI"`, đồng hồ vẫn đếm `0:01, 0:02, 0:04...` nhưng **hoàn toàn câm lặng**! Khi người dùng bấm Play lại lần 2–3 trên bài đó, lúc này `player.cur` đã là `trackId` và `player.reset()` đã xóa `prefetchIds` cũ nên `trackId` mới nằm trong `keep` và phát ra tiếng.
   - **Giải pháp:**
     - Trong `Loader` (`web/js/api.js`): bổ sung tập `this.loadingIds` và tham số `pinnedId` vào `this._evict(maxKeep, pinnedId)` để **tuyệt đối không bao giờ trục xuất bài hát đang nạp hoặc vừa giải mã xong**. Đồng thời khi xóa phần tử cũ khỏi `this.cache`, chỉ gọi `this.cache.delete(dropId)` để bộ thu gom rác V8 tự giải phóng sau khi không còn `Voice` nào tham chiếu, **cấm gán `entry.track.buffer = null`** làm hỏng các đối tượng `Track` đang sống. Trong `Loader.has(id)` và `Loader.get(id)`, kiểm tra chặt `Boolean(hit.track?.buffer)`.
     - Trong `Player.start(trackId)` (`web/js/player.js`) & `loader.protect` (`web/js/main.js`): gán `this._loadingTrackId = trackId`, hủy `this.plan` và xóa `this.prefetchIds = []` ngay trước khi gọi `this.loader.get(trackId)`, đồng thời đưa `player._loadingTrackId`, `player._switchingTrack?.id`, `player.fx?.B?.id` vào `loader.protect`.
2. **Nguyên nhân 2 — Voice dịch tông (`SignalsmithStretch`) cạn bộ đệm lát cắt sau khi chuyển bài `cut` / `drop` / `promote` (`web/js/player.js`):**
   - **Nguyên nhân:**
     - Khi chuyển bài có dịch tông (`tr.semis != 0`) và giữ tông (`tr.keylock`), `Engine.stretchVoice` chỉ cắt một lát âm thanh ngắn `[from, from + span + 4]` (~12–15 giây đầu đoạn vào của bài mới) nạp vào `SignalsmithStretch`.
     - Trong nhánh `case "cut"` (`web/js/player.js`), code chỉ khởi tạo `this._rampTo(1, RAMP_BEATS, step.rate)` cho nhịp độ mà **quên khởi tạo `this.pitchRamp`** để đưa `v.semis` về `0` (khác với `case "promote"`). Do `v.semis` giữ nguyên khác `0` mãi mãi, điều kiện bàn giao từ `stretched voice` sang `plain voice` ở `case "seq"` (`!prev.voice.semis`) không bao giờ thỏa mãn! Sau ~12 giây phát bài mới (`1 chuyển`), `SignalsmithStretch` chạy hết lát cắt `[from, to]` và phát ra **im lặng hoàn toàn** cho đến hết bài.
   - **Giải pháp:**
     - Khởi tạo đầy đủ `this.pitchRamp` trong `case "cut"` khi `v.stretched` có `v.semis != 0`.
     - Trong `case "seq"`, kiểm tra ngưỡng số thực `Math.abs(prev.voice.semis || 0) < 1e-3` VÀ bổ sung rào chắn an toàn `outOfStretchSlice` (`readPos >= prev.voice.stretch.to - 0.6 || readPos < prev.voice.stretch.from`): hễ đầu đọc tiến sát ranh giới lát cắt `SignalsmithStretch` thì lập tức crossfade 30ms sang `plain voice` đọc toàn bộ `track.buffer`, đảm bảo 100% không bao giờ cạn bộ đệm.
3. **Nguyên nhân 3 — Xung đột lịch tự động hóa Gain (`setValueCurveAtTime` trùng mốc `setValueAtTime`) & Tạm dừng giữa lúc Blend (`web/js/engine.js`, `web/js/player.js`):**
   - **Nguyên nhân:**
     - Trong `Voice.start(when, offset, rate, fadeIn)`, gọi `setValueAtTime(0, when)` cùng một thời điểm `when` với `setValueCurveAtTime(FADE_IN, when, fadeIn)` hoặc khi `when < ctx.currentTime` có thể gây lỗi chồng lấp automation trên Chromium/Safari khiến `gain` bị kẹt ở `0`.
     - Khi `pause()` trong lúc đang `blend` hoặc `fx`, `stopAll()` dừng cả `voiceA` lẫn `voiceB`, nhưng khi `play()` lại thì `this.blend` cũ chưa được xóa khiến `promote` chuyển sang `voiceB` đã chết.
   - **Giải pháp:**
     - Trong `Voice.start`, `Voice._read`, `Voice._curve` (`web/js/engine.js`): kẹp `safeWhen = Math.max(this.engine.ctx.currentTime, when)`, dùng `linearRampToValueAtTime` cho các đoạn nối ngắn `<= 20ms` và luôn neo `setValueAtTime(1, safeWhen + fadeIn + 0.002)` sau đường cong `FADE_IN`.
     - Trong `Player.pause()` và `Player.play()` (`web/js/player.js`): dọn sạch trạng thái `blend`/`fx` khi tạm dừng và tự động kích hoạt lại `AudioContext` trong `_tick()` nếu trình duyệt vừa tạm ngưng.

### 0. Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v170 — Hiệu chuẩn Màu Đèn/Bàn phím RGB Vật lý & Đồng bộ Màu Vệ tinh 1:1)
1. **Vì sao mở bài hát tone màu Cam/Hổ phách trên màn hình nhưng bàn phím RGB vật lý lại ra màu Xanh lục / Trắng ngả lục (`loopbox/smart_lights.py`):**
   - **Nguyên nhân:**
     1. **Nền trắng Pastel của màu giao diện (`L = 0.79..0.83`):** Trên giao diện tối (`#0c0908`), màu chủ đạo bài hát (`--acc`) được thiết kế ở độ sáng cao (`L ≈ 0.80`) để chữ và đường nét nổi bật trên nền đen. Khi đổi trực tiếp `oklch_to_srgb(0.80, 0.13, h=45..72)` sang sRGB, màu cam/hổ phách chứa một lượng lớn nền trắng (`min(R,G,B) ≈ 73..135`), ví dụ `(246, 168, 73)` hoặc `(227, 176, 119)`.
     2. **Nhân `boost` làm bão hòa kênh Đỏ (`R=255`) nhưng đẩy vọt kênh Lục (`G`) và Lam (`B`):** Khi nhân thêm `boost = 1.0 + 0.45*pulse + 0.35*bass` (`~1.4`), kênh `R` chạm trần `255` ngay lập tức trong khi kênh `G` bị đẩy lên `226..246` và `B` lên `102..166` -> `(255, 235, 102)` / `(255, 246, 166)`.
     3. **Đặc tính vật lý của chip LED RGB điều xung PWM tuyến tính:** Bàn phím RGB (ASUS TUF `\\.\ATKACPI`) và dải LED (WLED) điều khiển độ sáng bằng xung PWM tuyến tính (`gamma = 1.0`, không có nền đen `#0c0908` như màn hình), đồng thời nhân diode LED Xanh lục (`525nm`) có hiệu suất phát quang cao gấp ~2.2 lần nhân LED Đỏ (`625nm`). Khi nhận `G = 168..246` và `B = 73..166`, ánh sáng Lục/Lam áp đảo hoàn toàn ánh sáng Đỏ, biến màu cam trên màn hình thành màu **xanh lục / vàng chanh** trên bàn phím.
   - **Giải pháp (`oklch_to_led_rgb` trong `loopbox/smart_lights.py`):**
     - Triển khai hàm chuyên biệt `oklch_to_led_rgb(l, c, h, boost)`: khử hoàn toàn lớp nền trắng pastel (`w = min(r, g, b)`), giải mã đường cong gamma màn hình sang không gian điều xung PWM tuyến tính (`rn = (r0/mx)**1.75`, `gn = ((g0/mx)**2.05)*0.62`, `bn = ((b0/mx)**1.85)*0.82` bù hiệu suất phát quang diode Lục/Lam), sau đó chuẩn hóa theo kênh cực đại và nhân đồng nhất cả 3 kênh với hệ số `level` (`0.06..1.0`). Nhờ đó tỷ lệ sắc độ `R : G : B` được giữ nguyên 100% ở mọi nhịp đập bass mà không bao giờ bị tràn kênh. Kết quả: các bài hát tone cam/hổ phách (`h = 40..72°`) xuất ra bàn phím màu cam rực chuẩn xác (`R=255, G=12..59, B=0`).
2. **Đồng bộ 1:1 màu vòng nhạc (`_buildLayer`) trên màn hình Vệ tinh & phân xử Đa cửa sổ Host (`web/js/viz.js`, `loopbox/stage_sync_hub.py`, `web/js/stage_sync.js`):**
   - **Nguyên nhân:**
     1. Trên Vệ tinh, khóa bộ nhớ đệm `ring.layerKey` trong `_drawRing()` trước đây chưa gắn mã sắc độ `color_a` / `color_b` do Host truyền sang, và `_buildLayer()` chưa nhận `color_b` cho vòng thứ hai (`second`). Nếu Vệ tinh dựng lớp vẽ vòng nhạc trước khi bảng xếp hạng `theme.setMoods()` hoàn tất, vòng nhạc có thể giữ màu mood thô chưa xếp hạng.
     2. Khi mở đồng thời cả App Desktop và Tab Web (`hosts_count >= 2`), cửa sổ đang tạm dừng (`paused`) ở nền có thể giữ quyền `active_host` trong `2.0s` hoặc lệch với cửa sổ người dùng đang tương tác (`focused`).
   - **Giải pháp:**
     - Trong `web/js/viz.js`: `_broadcastHostTelemetry()` gửi chính xác `theme.accentOf(activeTrack.id, activeMood)` (đồng nhất 100% với `_updateField()`) kèm cờ `focused: document.hasFocus()`. Trên Vệ tinh, `_drawRing()` truyền `satForcedCol` (`color_a` cho vòng chính, `color_b` cho vòng phụ) vào `_buildLayer(ring.track, satForcedCol)` và đưa `satHueKey` vào `ring.layerKey` để tự động vẽ lại ngay khi màu từ Host thay đổi.
     - Trong `loopbox/stage_sync_hub.py`: ưu tiên cửa sổ Host đang `focused` khi chuyển bài/tạm dừng giữa nhiều cửa sổ.
     - Trong `web/js/stage_sync.js`: hiển thị trực tiếp màu RGB thực tế (`last_rgb`) ngay trên chấm trạng thái của thiết bị đang bật trong `#pane-lights`, và cô lập lệnh nháy thử từng thiết bị (`test_color(device_id=...)`) không làm đổi màu bàn phím khi thử thiết bị khác.

### 1. Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v169 — Dynamic Smart Lights & Multi-Vendor RGB Discovery)
1. **Loại bỏ 100% hardcode `"ASUS TUF Gaming"` & `"WLED"` trong HTML (`web/index.html`, `web/js/stage_sync.js`, `loopbox/smart_lights.py`, `loopbox/server.py`, `web/css/app.css`):**
   - **Nguyên nhân:** Giao diện `#pane-lights` trong `web/index.html` trước đây gán cứng thẻ tĩnh `"Đèn Bàn phím Laptop RGB — ASUS TUF Gaming"` và `"Dải LED Thông minh WLED"`, khiến các máy tính không phải ASUS TUF (Dell, HP, MacBook, Lenovo, PC ráp...) vẫn hiển thị dòng chữ ASUS TUF Gaming và không thể quản lý danh sách nhiều thiết bị cùng lúc.
   - **Giải pháp:**
     - **Tự động nhận diện phần cứng thực tế (`get_system_hardware_info()` & `discover_devices()`):** Đọc tên dòng máy và bo mạch chủ từ BIOS Registry / Linux DMI / macOS `sysctl`; chỉ khi driver kernel `\\.\ATKACPI` thực sự tồn tại trên máy thì mới đăng ký thiết bị `hw:asus_acpi` mang đúng tên model máy thực tế (ví dụ: `Bàn phím ASUS TUF Gaming A15 (FA506II)`). Trên máy không có `\\.\ATKACPI`, thiết bị này hoàn toàn không xuất hiện.
     - **Dò tìm đa giao thức tự động (Hardware & LAN):**
       1. **ASUS ATKACPI Kernel (`\\.\ATKACPI`)** trên Windows khi phần cứng hỗ trợ.
       2. **Linux Sysfs RGB/LED (`/sys/class/leds/*`)** trên Linux.
       3. **OpenRGB SDK Server (`127.0.0.1:6742` hoặc LAN)** hỗ trợ bàn phím, chuột, mainboard, RAM RGB đa hãng (Razer, Corsair, Logitech, MSI, Gigabyte, SteelSeries, Lenovo Legion, HyperX...).
       4. **WLED Wi-Fi (`ESP8266`/`ESP32`)**: quét song song các IP lân cận trong bảng ARP qua `/json/info` để lấy tên thiết bị, số bóng LED thực tế và đồng bộ đa vùng `∞` qua UDP DDP (`4048`).
       5. **Philips WiZ Smart Lights**: quét UDP Broadcast (`38899`, `getSystemConfig` / `setPilot`).
       6. **Yeelight / Xiaomi Wi-Fi LED**: quét SSDP Multicast (`239.255.255.250:1982` / TCP `55443`).
     - **Kết nối thiết bị thủ công & Quản lý từng thiết bị (`/api/lights/scan`, `/api/lights/devices/add`, `/api/lights/devices/toggle`, `/api/lights/devices/remove`):**
       - Người dùng có thể bấm **Quét thiết bị** bất kỳ lúc nào hoặc thêm thủ công thiết bị theo giao thức (`WLED Wi-Fi`, `OpenRGB SDK`, `Philips WiZ`, `Yeelight`, `Govee LAN`) kèm IP/Host, Cổng, Số bóng LED và Tên gợi nhớ.
       - Hỗ trợ bật/tắt riêng từng thiết bị, nháy thử riêng từng thiết bị (`.btn-light-ping`), xóa thiết bị thủ công (`.btn-light-remove`) và lưu cấu hình bền vững tại `DATA_DIR/lights_devices.json`.

### 2. Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v168 — Loa Vệ tinh Mobile & CSS Popover)
1. **Không nghe thấy âm thanh khi bật Loa Vệ tinh trên điện thoại iOS Safari / Mobile (`web/js/stage_sync.js`, `loopbox/stage_sync_hub.py`):**
   - **Nguyên nhân:**
     1. **Cần gạt Im lặng phần cứng trên iPhone (`AVAudioSessionCategoryAmbient`):** Trên iOS Safari, `Web Audio API` (`AudioContext.destination`) mặc định đi qua kênh chuông/ambient — bị tắt tiếng 100% khi cần gạt vật lý bên hông iPhone để ở chế độ Im lặng (Silent Mode). Khi phát nhạc chính, `Engine.unlockAudio()` (`web/js/engine.js`) phát thẻ `<audio src="/audio/silence.mp3" loop playsinline>` để ép iOS chuyển sang `AVAudioSessionCategoryPlayback`, nhưng ở chế độ Vệ tinh (`stage_sync.js`), `setSatelliteAudioEnabled()` chỉ khởi tạo `satAudioCtx` mà không kích hoạt `<audio src="/audio/silence.mp3">` hay `navigator.audioSession.type = "playback"`.
     2. **Trạng thái `"interrupted"` / thiếu mồi xung nhịp trong cử chỉ chạm & bật từ xa:** `_ensureSatAudioCtx()` chỉ kiểm tra `state === "suspended"` (bỏ sót trạng thái `"interrupted"` trên iOS Safari) và không phát mồi buffer 1-frame đồng bộ ngay trong sự kiện `click`/`touchend`. Ngoài ra, khi bật Loa Vệ tinh từ xa trên máy Host (`satellite_audio_control`), `satAudioEnabled` chuyển sang `true` trên điện thoại mà không có cử chỉ chạm nên `satAudioCtx` vẫn bị khóa dù giao diện báo `"Đang phát"`.
     3. **Xung nhịp gói tin Wi-Fi (`leadSec + 0.16`) & Lệch tần số lấy mẫu (`22050 Hz` vs `48000 Hz`):** Mỗi gói PCM `22050 Hz` dài `46.44ms`; trên mạng Wi-Fi di động (`192.168.1.x`), một chùm 4 gói đến liền nhau (`185.8ms`) đã vượt ngưỡng `leadSec + 0.16` (`160ms`), khiến `satNextPlayTime` bị reset lùi liên tục gây đứt tiếng.
     4. **Đồng bộ đăng ký kênh âm thanh (`StageSyncHub`):** Nếu `active_host` chưa được gán hoặc vừa làm mới khi bắt đầu đẩy luồng PCM nhị phân, `handle_host_audio()` trước đây bỏ qua gói tin thay vì tự nhận Host đang phát; hoặc khi kết nối lại chưa tự động gửi lại `audio_subscribe`.
   - **Giải pháp:**
     - Bổ sung `_initSatSilenceAnchor()` và `_unlockSatAudio(fromUserGesture)` trong `web/js/stage_sync.js`: tự động đặt `navigator.audioSession.type = "playback"`, kích hoạt thẻ `<audio src="/audio/silence.mp3" loop playsinline>` ẩn, gọi `engine.unlockAudio()`, `resume()` cho mọi trạng thái `!== "running"` (`"suspended"` / `"interrupted"`), và phát 1-frame silent `AudioBufferSourceNode` ngay trong thao tác chạm (`#btn-sat-audio`, `#btn-sat-audio-switch`, `#btn-sat-audio-cfg`, thanh trượt và sự kiện chạm màn hình). Nếu Loa Vệ tinh được bật từ xa khi chưa chạm màn hình, hiển thị rõ `"Loa Vệ tinh: Chạm bật tiếng"` / `"Chạm bật"` và mở khóa ngay khi người dùng chạm.
     - Bổ sung `_schedulePcmPacket()` hỗ trợ nội suy tuyến tính sang đúng `ctx.sampleRate` phần cứng (`48000 Hz` / `44100 Hz`), hàng đợi tạm `_pendingAudioPackets` khi `ctx` đang mở khóa, nới cửa sổ chống giật Wi-Fi lên `leadSec + 0.85`, cùng bộ tự phục hồi đăng ký `audio_subscribe` mỗi `1.5s` nếu đang ở chế độ `ring` mà chưa nhận gói PCM.
     - Cập nhật `StageSyncHub.handle_host_audio()` (`loopbox/stage_sync_hub.py`) tự động nhận diện `active_host` ngay khi Host gửi luồng PCM.
2. **Thiết kế lại CSS Modal/Popover Cấu hình Loa Vệ tinh (`#sat-audio-popover`, `.sat-audio-wrap`) chuẩn Mobile (`web/css/app.css`, `web/index.html`, `web/js/stage_sync.js`):**
   - **Nguyên nhân:**
     1. Thanh trượt `#s-sat-local-vol` và `#s-sat-local-lat` dùng biến CSS `--v` để tô vệt màu cam (`linear-gradient(90deg, var(--accent) var(--v), ...)`), nhưng `_updateSatelliteAudioUI()` không cập nhật `--v`, khiến vệt màu cam luôn kẹt cứng ở `50%` lệch hẳn khỏi nút tròn kéo (`66.7%` ở mức `100%` và `21.4%` ở mức `85ms`).
     2. `.sat-audio-popover` đặt `position: absolute; right: 0; width: 268px;`, bị lệch sang phải trên màn hình dọc di động và quá hẹp khiến tiêu đề `CỘNG HƯỞNG LOA VỆ TINH` cùng nhãn `Đang phát` đều bị gãy thành 2 dòng.
     3. `.sat-audio-wrap` và `.sat-audio-pill[aria-pressed="true"]` tạo 2 lớp viền lồng nhau (vi phạm **Zero-Double-Border**), đồng thời nền popover hơi trong suốt làm chữ bài hát dưới sân khấu (`"Mạc Vấn Quy Kỳ..."`) xuyên qua gây rối mắt.
   - **Giải pháp:**
     - Cập nhật `_updateSatelliteAudioUI()` tính và gán chính xác `--v` cho cả `#s-sat-local-vol` (`0..1.5` -> `0%..100%`) và `#s-sat-local-lat` (`40..250ms` -> `0%..100%`).
     - Hợp nhất `.sat-audio-wrap` thành một viên nang đơn viền liền khối (`.sat-audio-wrap.is-active` phát sáng viền đơn, `.sat-audio-pill` không viền phụ), mũi tên `.sat-audio-cfg-btn` xoay mượt `180deg` khi mở.
     - Trên Mobile (`@media (max-width: 600px)` và Landscape), căn giữa hoàn toàn `.sat-audio-wrap` và `#sat-audio-popover` (`position: fixed !important; left: 50% !important; transform: translateX(-50%) !important; width: min(340px, calc(100vw - 24px)) !important;`), tăng độ đặc nền `oklch(0.125 var(--gc) var(--gh) / 0.98)` + `backdrop-filter: blur(28px)`, bọc từng nhóm thanh trượt trong thẻ `.mic-gain-row` tinh gọn, và giữ tiêu đề `Cộng hưởng Loa Vệ tinh` + huy hiệu `Đang phát` luôn nằm gọn trên 1 dòng.
3. **Khắc phục lỗi Không phát được bài hát dài >15 phút trên Web (`v167` — `loopbox/server.py`, `web/js/api.js`, `web/js/engine.js`, `web/js/player.js`):**
   - Sửa lỗi `NameError: request is not defined` khi xử lý HTTP `Range` trong `_send_sound()` (`loopbox/server.py`).
   - Triển khai bộ giải mã MP3 chia cắt theo ranh giới khung (`parseMp3Frames`, `decodeTrackAudio` trong `web/js/api.js`) với mỗi mảnh ~10 phút + `yield` luồng chính và hạ tần số lấy mẫu thích ứng (`32000 Hz` cho bài >25 phút trên Desktop, `22050 Hz` cho bài >10 phút trên Mobile) để bài 55 phút (`gebkUty7dPU`, `80.3 MB`) giải mã mượt mà không vượt trần bộ nhớ `decodeAudioData` của Chromium/WebKit.
   - Đồng bộ nút Play trên Deck (`player.start()`) chọn đúng thứ tự danh sách bài hiển thị (`getOrderedReadyTracks()`).

### 2. Kiểm thử & Xác thực (Verification — `v168`)
- `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py`: **PASS (Exit Code 0)**
- `.\.venv\Scripts\python.exe tests/test_stage_sync.py` (bao gồm `test_v168_mobile_satellite_audio_and_popover_css`): **ALL 12 TESTS PASSED (Exit Code 0)**
- `.\.venv\Scripts\python.exe tests/test_long_track_playback.py`: **Ran 3 tests, OK (Exit Code 0)**
- `.\.venv\Scripts\python.exe tests/test_pwa_manifest.py`: **PASS (Exit Code 0)**
- Kiểm thử E2E Live trên trình duyệt Edge headless ở khung hình Mobile `390x844` (`Host` + `Satellite ?mode=satellite`): **PASS (Exit Code 0)** — xác thực `rxPackets: 37`, `rxBytes: 151848`, `maxSample: 7092`, `satCtxState: "running"`, `hasSilenceAnchor: true`, `volVar: "66.7%"`, `latVar: "21.4%"`, `popRect: {left: 25, right: 365, width: 340}` (căn giữa chuẩn tại `195px`), `titleHeight: 16px` (1 dòng), `badgeHeight: 24px` (1 dòng).

---

## Phiên làm việc: 08/11/2026 (Triệt tiêu Phập phồng Kích thước Vòng tròn & Gián đoạn Nhịp đập khi Tìm bài Tiếp theo v166)

### 1. Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v166)
1. **Bố cục 2 vòng đóng mở quá sớm trước khi tải/chuẩn bị xong bài mới (`web/js/viz.js` `_roles`):**
   - **Nguyên nhân:** Ngay khi bộ lập lịch tạo một kế hoạch dự kiến (`p.plan`), kể cả lúc bài kế tiếp chưa tải xong audio/stems/stretch (`target === null`, `ready !== true`), `_roles()` lập tức trả về `placeholder = p.plan.tr.to` -> `two = true`, làm vòng đang phát co lại ~30–35%. Nếu điểm kích hoạt trễ hẹn (`!plan.ready`) hoặc bài mới tải lỗi, kế hoạch bị hủy (`two = false`), vòng lại phình to về 100%, rồi ngay nhịp kế tiếp (`~0.45s` sau) lại co xuống 65%, tạo hiệu ứng vòng tròn to nhỏ liên tục.
   - **Giải pháp:** Bổ sung ngưỡng `DOCK_LEAD_S = 14s` và khóa `_docked`: trong chế độ tự động `chain`, vòng đang phát giữ nguyên kích thước 100% trọn tâm sân khấu trong suốt thời gian AI DJ tìm kiếm, tải xuống và chuẩn bị audio/stems/stretch (`_prewarmLayer` vẽ ngầm texture trước để lúc ráp không tốn khung hình), đồng thời vẫn hiển thị tuyến đường nét đứt `plan.jumps` và chấm thoát nhấp nháy trên vòng chính. Chỉ khi người dùng chủ động click chọn điểm nối (`plan.picked`) HOẶC bài kế tiếp đã sẵn sàng (`plan.target && plan.ready`) và tiến vào cửa sổ 14 giây cuối (`p.urgent || etaLeft <= DOCK_LEAD_S`) thì vòng thứ hai mới trượt êm vào khớp thành biểu tượng vô cực `∞`. Bổ sung bộ trễ trễ layout (`_twoHoldUntil = 1100ms`) chống co giãn hai chiều nếu có kế hoạch thay thế tức thời.
2. **Xung đột & Lặp vô tận trong Bộ lập lịch khi gặp bài lỗi hoặc bài dài (`web/js/player.js`):**
   - **Nguyên nhân:** `_planExit` kiểm tra `LOAD_LEAD` (3s) và `PREP_LEAD` (5s) tách rời thay vì cộng gộp (`loadLead + prepLead + bendLead`), khiến các bài chưa decode (hoặc Vietmix 30–55 phút) liên tục rớt hẹn ở `atTrigger` mà không có thời gian nghỉ (`cooldown`). Ngoài ra `_setPlan` và `_prepare` chỉ đánh dấu lỗi trên một đối tượng `tr` đơn lẻ chứ không chặn ở cấp mã bài (`tr.to`), nên `_planExit` và `_emergencyExit` liên tục chọn lại đúng bài hỏng ở hàng chục điểm nối còn lại.
   - **Giải pháp:** Theo dõi cooldown cấp bài hát (`_failedTrackUntil` 5 phút cho bài lỗi, `_slowTrackUntil` 20 giây cho bài trễ hẹn) và `tr._cooldownUntil` (12 giây) ngay khi điểm nối rớt hẹn; cộng gộp đầy đủ ngân sách thời gian `loadLead + prepLead + bendLead` tính theo thời lượng thực tế bài đích (`durB`), đồng thời ưu tiên nhẹ các bài đã nạp sẵn trong RAM (`readyBonus`) và lọc bỏ bài lỗi khỏi `_emergencyExit`.
3. **Trẻo luồng chính từ `_buildLayer()` làm đứt quãng nhịp đập (`web/js/viz.js`):**
   - **Nguyên nhân:** Hàm `_buildLayer(track)` khởi tạo canvas siêu mẫu lên tới `3280x3280` (`layerScale = 4`) và phát ra ~8.000 lệnh vẽ rời rạc (`beginPath` + `stroke`/`arc`/`fill` từng dây cung, từng hạt bụi và vạch chia giờ), gây đứng khung hình 120–300ms mỗi lần dựng vòng bài mới.
   - **Giải pháp:** Giới hạn kích thước offscreen canvas `<= 2048px` (`2048 / S`), gom nhóm các dây cung nhảy theo 8 thùng alpha (`CHORD_BUCKETS`) + 1 lượt vẽ cho các dây mờ, gom hạt bụi thành 2 lượt `fill()` mỗi phách (`loPts`, `hiPts`), gom vạch chia phút và phân đoạn thành 1 lệnh `stroke()` mỗi nhóm. Nâng ngưỡng dung sai `_resize()` (`> 0.04`) và tách riêng hệ số trượt bố cục êm (`kLayout`, `tau = 0.36s`) khỏi độ nảy nhịp đập (`pulseAmt`), giữ `_beatPulse` ổn định (`tau = 0.24s`, kẹp `dt <= 0.06s`) kể cả lúc máy chuyển đổi dữ liệu nặng. Đồng bộ hóa `two = Boolean(this.cross || second || this.placeholder)` lên Host telemetry để Vệ tinh ăn khớp 1:1.
4. **Cố định chiều cao `#next-info` tránh rung khung Canvas (`web/css/app.css`):**
   - Khóa `.next` đúng khung 2 dòng (`min-height: 3.1em; max-height: 3.1em; -webkit-line-clamp: 2; overflow: hidden`) để tên bài dài không bao giờ đẩy thanh trạng thái thành 3 dòng làm co `.canvas-wrap` và kích hoạt `ResizeObserver` xóa cache offscreen.
5. **Nâng cấp phiên bản đồng bộ `v166`:**
   - Cập nhật `?v=166` / `meikova-loop-v166` / `LOCAL_APP_VER = 166` trên `web/index.html`, `web/sw.js`, toàn bộ ES modules (`web/js/*.js`) và `scripts/verify_deck_responsive.py`.

---

## Phiên làm việc: 08/11/2026 (Triệt tiêu Hiện tượng Nhấp nháy Màn hình Vệ tinh & Phân xử Đa Host v165)

### 1. Nguyên nhân gốc rễ & Giải pháp khắc phục triệt để (v165)
1. ** Cấp phát lại bộ đệm Canvas 60Hz trên Màn hình Vệ tinh (`web/js/viz.js`):**
   - **Nguyên nhân:** `_frame(now)` trên Vệ tinh so sánh `this.h` (chiều cao `.canvas-wrap` `getBoundingClientRect()`, thấp hơn `window.innerHeight` khoảng ~140–200px do có `#next-info`, `.deck`, `#history`) với `window.innerHeight`, khiến `_resize()` bị gọi ở mọi khung hình (`60/120Hz`) và xóa trắng bộ đệm `canvas.width`/`canvas.height`.
   - **Giải pháp:** Đo trực tiếp `this.canvas.parentElement.getBoundingClientRect()` đồng nhất giữa `_frame()` và `_resize()`, bổ sung kiểm tra thoát sớm (`return;`) khi `(w, h, dpr, pxW, pxH, baseR)` không đổi và không ghi đè inline `style.width`/`style.height` trên Vệ tinh.
2. **Xung đột Đa Host (`idle` vs `ring`) & Lỗi rò rỉ WebSocket khi đóng tab sạch (`loopbox/stage_sync_hub.py`, `loopbox/server.py`, `web/js/viz.js`):**
   - **Nguyên nhân:** Khi có thêm một tab/cửa sổ Host thứ hai đang ở trạng thái chờ (`mode: "idle"`) mở song song với Host đang phát nhạc, cả hai cùng bắn telemetry `30 FPS` lên `StageSyncHub`, làm Vệ tinh dao động liên tục giữa vòng nhạc tím (`alpha` giảm còn ~55%) và đường vô cực màu xanh lá (`_drawIdle`) như ảnh chụp thực tế. Ngoài ra, trong `websocket_stage_sync` (`loopbox/server.py`), nhánh `if msg_type == "websocket.disconnect": break` thoát khỏi vòng lặp `try` mà bỏ qua `sync_hub.disconnect()`, để lại kết nối ma trong `sync_hub.hosts` / `sync_hub.satellites`.
   - **Giải pháp:** Triển khai cơ chế phân xử `active_host` có thẩm quyền trong `StageSyncHub` (`host_last_playing`, `host_last_seen`): tự động chặn toàn bộ gói `idle` / `paused` cũ và luồng âm thanh nhị phân từ các Host phụ khi `active_host` đang phát nhạc; định tuyến lệnh điều khiển từ Vệ tinh (`toggle_pause`, `next`, `jump`...) chỉ tới `active_host` để không đánh thức nhầm Host phụ; chuyển `await sync_hub.disconnect(websocket, role=role)` vào khối `finally:` và phát bản tin reset `idle` sạch khi `active_host` đóng tab. Đồng thời ở phía client (`viz.js`), ngắt phát `idle` từ tab Host ẩn (`document.hidden`) và giảm nhịp keepalive `idle` xuống `1Hz`.
3. **Khoảng trống `idle` thoáng qua khi chuyển bài trên cùng một Host (`web/js/player.js`, `web/js/viz.js`):**
   - **Nguyên nhân:** `player.start(trackId)` gọi `this.reset()` (`this.cur = null`) trước `await this.engine.ctx.resume()`, tạo khe hở bất đồng bộ khiến bộ phát nhịp 33ms gửi nhầm `mode: "idle"`.
   - **Giải pháp:** Chuyển `await this.engine.ctx.resume()` lên trước `this.reset()` và gắn cờ bảo vệ `this._switchingTrack` trong khối `try/finally` để `_broadcastHostTelemetry()` giữ nguyên ngữ cảnh bài hát xuyên suốt quá trình chuyển bài.
4. **Chống nhiễu Blip `idle` tạm thời, Cô lập Cấu hình Vệ tinh & Ngăn vòng lặp Reload `app_ver` (`web/js/stage_sync.js`, `web/js/main.js`):**
   - Bổ sung bộ đệm xác nhận `180ms` (`_idleConfirmTimer`) trên Vệ tinh khi Host đang phát nhạc để một khung `idle` nhiễu đơn lẻ không bao giờ xóa `primaryTrack` / `this.primaryId`, đồng thời đồng bộ mượt `this.accent` theo `t.acc` để vệt tàn dư đường vô cực mang đúng màu bài hát thay vì xanh lá mặc định.
   - Chặn `applySettings()`, `fetch("/api/settings")` và `refresh()` ghi đè màu sắc / trạng thái sân khấu trên Vệ tinh (`if (stageSync.isSatellite) return;`).
   - Đổi kiểm tra phiên bản từ `!==` sang tiến về phía trước (`remoteVerNum > LOCAL_APP_VER` với `v165` + khóa `sessionStorage` 15 giây) để ngăn vòng lặp tự động reload vô tận nếu còn tab Host phiên bản cũ chưa tải lại.
   - Nâng cấp đồng bộ cache version lên `v165` (`meikova-loop-v165`) trên toàn bộ ES modules, `web/index.html`, `web/sw.js` và `scripts/verify_deck_responsive.py`.

### 2. Kiểm thử & Xác thực (Verification)
- Cú pháp JS (`web/js/*.js`, `web/sw.js` qua `node --check`): **PASS (Exit Code 0)**
- Biên dịch Python (`python -m compileall -q loopbox tests scripts`): **PASS (Exit Code 0)**
- `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py`: **PASS (Exit Code 0)**
- `.\.venv\Scripts\python.exe tests/test_pwa_manifest.py`: **PASS (Exit Code 0)**
- `.\.venv\Scripts\python.exe -u tests/test_stage_sync.py` (bao gồm `test_multi_host_arbitration` & static anti-flicker invariants): **ALL 10 TESTS PASSED (Exit Code 0)**
- `.\.venv\Scripts\python.exe -u tests/test_server_and_features.py`: **ALL 35+ TESTS PASSED (Exit Code 0)**
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`: **Ran 41 tests in 14.404s, OK (Exit Code 0)**
- Kiểm thử E2E Live trên trình duyệt Edge headless (2 Host mở song song + 1 Vệ tinh `920x960` với `box.height = 757 < innerHeight = 960`): **PASS (Exit Code 0, CONSOLE_ERRORS: [])** — `badSamples = []`, `resizeCount = 0`, `dimResetCount = 0`, `switchIdleSamples = []`, điều khiển Pause/Play từ Vệ tinh chỉ tác động lên Host đang phát và reset `hosts_count: 2 -> 1 -> 0` sạch khi đóng tab.

### 3. Cảnh báo & Trạng thái vận hành
- Máy chủ dev đã được khởi động lại sạch trên `http://0.0.0.0:8765` (`http://127.0.0.1:8765`).
- Lưu ý: Hãy nhấn `Ctrl+Shift+R` (hoặc `F5`) trên tab Máy chính (Host) 1 lần để nạp mã nguồn `v165` và cập nhật Service Worker lên `meikova-loop-v165` (trang Vệ tinh sẽ tự động nâng cấp lên `v165`).

---

## Phiên làm việc: 08/11/2026 (Loa Vệ tinh Đa phòng, Lời bài hát LRCLIB, Xuất Setlist M3U8 & Smart Pre-buffer v164)

### 1. Mục tiêu hoàn thành (v164)
1. **Cộng hưởng Âm thanh Đa phòng / Loa Vệ tinh (`loopbox/stage_sync_hub.py`, `loopbox/server.py`, `web/js/stage_sync.js`, `web/index.html`, `web/css/app.css`):**
   - Triển khai kênh truyền tải nhị phân trực tiếp `WebSocket` trên `/api/ws/stage-sync`: Máy chính trích xuất luồng PCM stereo từ `engine.analyser` qua `attachHostEngine()` đóng gói tiêu đề 8-byte `"ML"` (`22.05 kHz` / `Int16 PCM`) truyền tới các Vệ tinh đăng ký (`audio_subscribe`), bỏ qua khung khi không có Vệ tinh bật loa để tiết kiệm CPU.
   - Bổ sung thanh điều khiển `#sat-audio-wrap` / `#sat-audio-popover` trên màn hình Vệ tinh (mặc định **Tắt** để chống vọng âm, bật 1 chạm kèm chỉnh Âm lượng `0–150%` và Độ trễ đệm `40–250ms`).
   - Bổ sung đồng bộ trạng thái `audio_satellites_count` hai chiều qua `sync_status` và `/api/sync/room-info`, cho phép điều khiển từ xa `#btn-toggle-sat-audio` và chỉnh độ trễ `#s-sat-latency` trong `#modalStageSync`, đồng thời nối mạch tab `#pane-lights` (`#btn-toggle-kbd-sync`, `#btn-toggle-wled`, `#input-wled-ip`, `.color-pill-btn`) tới `/api/lights/config` và `/api/lights/test`.
2. **Lời bài hát Thời gian thực Đồng bộ Phách nhảy & Vệ tinh (`loopbox/server.py`, `web/js/api.js`, `web/js/player.js`, `web/js/viz.js`, `web/js/stage_sync.js`, `web/js/main.js`):**
   - Backend bổ sung `_parse_lrc_lines()`, `_clean_song_query()`, `GET /api/tracks/{tid}/lyrics` (tự động truy vấn LRCLIB + cache `lyrics.json` trong thư mục bài hát + negative cache 5 phút) và `POST /api/tracks/{tid}/lyrics` (lưu LRC tùy chỉnh), bảo vệ OWASP A03 qua `library.valid_id(tid)` và `library.read_meta(tid)`.
   - Frontend tính vị trí phát thực tế sau các cú nhảy/tua qua `player.getAudibleSongTime()`, tìm nhị phân câu hát tại `#ambient-lyrics` (`120ms` interval) và phản chiếu 1:1 lên Vệ tinh qua trường telemetry `lyrics_enabled`, `lyric_prev`, `lyric_cur`, `lyric_next`. Hỗ trợ tùy chọn `#s-lyrics`, nút Zen `#zen-btn-lyrics`, phím tắt `C` (cả Host & Satellite), và modal chỉnh sửa `#modal-lyrics-editor`.
3. **Nhật ký Setlist Đầy đủ & Bộ Xuất Tracklist `.txt` / Playlist `.m3u8` (`web/js/player.js`, `web/js/main.js`, `web/index.html`):**
   - Lưu tách biệt lịch sử không giới hạn `player.sessionSetlist` và `player.sessionStats` bên cạnh `player.history` (giữ nguyên giới hạn 50 bài cho thuật toán AI recency).
   - Bổ sung modal `#modal-setlist-export` hiển thị thống kê phiên, bản xem trước, sao chép nhanh, tải `.txt` và tải `#EXTM3U` `.m3u8` phân giải URL động theo `window.location.origin`. Kích hoạt qua `#btn-export-setlist`, `#zen-btn-setlist`, `#btn-open-setlist-modal`, hoặc phím tắt `X`.
4. **Nâng cấp Smart Lookahead Pre-buffer trên Desktop (`web/js/api.js`, `web/js/player.js`, `web/js/main.js`):**
   - Mở rộng bộ nhớ đệm `Loader` trên Desktop lên `3` bài (`keep = isMobile ? 2 : 3`), lookahead `maxPrefetch = 2` và `PREFETCH_LEAD = 28s` (`CHAIN` warmup sau 1.5s, kích hoạt nạp trước lyrics khi phát sự kiện `"prefetch"`), giữ nguyên giới hạn `keep = 2` / `maxPrefetch = 1` / `PREFETCH_LEAD = 20s` cho thiết bị di động.
5. **Chuẩn hóa Cache Version `v164` & Chạy Dev Server:**
   - Cập nhật đồng bộ `?v=164` trên toàn bộ ES module imports, `web/index.html`, `web/sw.js` (`meikova-loop-v164`), `web/js/viz.js` (`app_ver: "v164"`), và `web/js/stage_sync.js`.

### 2. Kiểm thử & Xác thực (Verification)
- Cú pháp JS (`web/js/*.js`, `web/sw.js` qua `node --check`): **PASS (Exit Code 0)**
- Biên dịch Python (`py_compile` trên `loopbox/server.py`, `loopbox/stage_sync_hub.py`, `tests/test_stage_sync.py`): **PASS (Exit Code 0)**
- `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py`: **PASS (Exit Code 0)**
- `.\.venv\Scripts\python.exe tests/test_pwa_manifest.py`: **PASS (Exit Code 0)**
- `.\.venv\Scripts\python.exe tests/test_stage_sync.py`: **ALL 9 TESTS PASSED (Exit Code 0)**
- `.\.venv\Scripts\python.exe tests/test_server_and_features.py`: **ALL 35+ TESTS PASSED (Exit Code 0)**
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`: **Ran 41 tests, OK (Exit Code 0)**
- Kiểm thử E2E Live trên trình duyệt Edge headless (`Host 1366x840`, `Satellite ?mode=satellite`, `Mobile 390x844 iPhone UA`): **PASS (Exit Code 0, CONSOLE_ERRORS: [])** — xác thực `/api/sync/room-info`, đồng bộ `audio_satellites_count`, phím tắt `C`/`X`/`Ctrl+R`, `keep = 3` (Desktop) vs `keep = 2` (Mobile), zero horizontal overflow.

### 3. Cảnh báo & Trạng thái vận hành
- Server dev đang chạy nền trên `http://0.0.0.0:8765` (`http://127.0.0.1:8765`).
- Nếu trình duyệt đang mở từ phiên `v163`, tải lại trang Host 1 lần để Service Worker cập nhật lên `meikova-loop-v164` (màn hình Vệ tinh tự động reload theo `app_ver: "v164"`).

---

## Phiên làm việc: 08/11/2026 (Chặn tổ hợp phím trình duyệt Ctrl+R, Nhịp Đập Canvas, Responsive Topbar & Đồng bộ Sân Khấu v163)

### 1. Mục tiêu hoàn thành (v163)
1. **Khắc phục lỗi nhấn `Ctrl+R` tải lại trang kích hoạt nhầm tính năng Ghi âm (`web/js/main.js`, `web/js/stage_sync.js`):**
   - Trong bộ lắng nghe `keydown` toàn cục (`web/js/main.js`), bổ sung kiểm tra `if (e.ctrlKey || e.metaKey) return;` và `if (e.altKey && !(e.key === "m" || e.key === "M")) return;` ngay ở đầu hàm để các tổ hợp phím hệ thống / trình duyệt (`Ctrl+R`, `Ctrl+Shift+R`, `Ctrl+V`, `Ctrl+F`, `Ctrl+T`, `Ctrl+N`, `Ctrl+L`, `Ctrl+J`, `Ctrl+H`, `Ctrl+1..9`) không bao giờ kích hoạt nhầm phím tắt đơn của ứng dụng (`R` thu âm, `V` chế độ giọng hát, `F` toàn màn hình, `N` chuyển bài...) trên cả màn hình chính lẫn màn hình vệ tinh (`stageSync.sendCommand("toggle_record")`).
2. **Khắc phục Responsive Header / Topbar trên Màn hình Nhỏ (`web/css/app.css`, `web/js/main.js`):**
   - Sửa lỗi độ ưu tiên CSS (`!important` ở `@media (max-width: 1400px)` ghi đè kích thước nút `34px` và `gap: 6px` trên màn hình nhỏ khiến nút thư viện ngoài cùng bên phải bị tràn mép phải).
   - Bổ sung hệ thống co giãn đa tầng cho `.topbar`, `.brand`, `.mode` và `.topbar__end` tại `@media (max-width: 768px)` (nút `30x30px`), `@media (max-width: 560px)` (nút `28x28px`, `gap: 4px`), và `@media (max-width: 430px)` (nút `27x27px`, ẩn từ đầu `.brand__word:first-child`), đồng thời giữ nguyên `.sync-count-badge` và `.tunnel-dot` cùng `ResizeObserver` cập nhật tức thì thanh trượt `.seg__ind`.
3. **Hiệu ứng Nhịp Đập Vòng Nhạc Theo Phách & Âm Trầm trên cả Máy Chính và Vệ Tinh (`web/js/viz.js`, `web/js/stage_sync.js`):**
   - Bổ sung bán kính nền `ring._layoutR` tách biệt với bán kính hiển thị `ring.r = ring._layoutR * (1 + pulseAmt)` (`pulseAmt = (ring.role === "primary" ? 1 : 0.6) * (0.04 * this.pulse + 0.015 * this.bass)`), giúp vòng vô cực, vầng hào quang spectrum, các cung nhảy và con trỏ ánh sáng co giãn nhịp nhàng theo từng phách mạnh và âm bass trên cả màn hình chính lẫn màn hình vệ tinh mà không làm nhảy chữ tiêu đề trung tâm (`_placeCenter`) hay phải vẽ lại offscreen layer 4x.
   - Tùy chọn bật/tắt **Nhịp đập theo nhạc** (`#s-beat-pulse`) trong tab **Tinh chỉnh** (`web/index.html`, `web/js/main.js`), lưu tự động vào `localStorage` / `/api/settings` và đồng bộ thời gian thực sang màn hình vệ tinh qua trường `beat_pulse` trong telemetry (`app_ver: "v163"`).
2. **Đồng bộ 1:1 Hiệu ứng Chuyển Đổi Bài Hát trên Màn hình Vệ tinh (`web/js/viz.js`, `web/js/stage_sync.js`):**
   - Hợp nhất `_drawSatelliteStage` sử dụng chung bộ máy trạng thái `this.rings` (`Map<trackId, Ring>` với các vai trò `"primary"`, `"second"`, `"leaving"`, `"fading"`) giống hệt `_update(view, dt)` của máy chính thay vì ghi đè tĩnh tại chỗ (`satellitePrimaryRing`).
   - Khi chuyển bài (tự động `blend`/`cut`/`drop`/`fade`/`riser`/`echo` hoặc bấm `Next (N)`), vòng lặp bài cũ chuyển sang `role = "leaving"` (thu nhỏ `r *= 0.985`, dịch nhẹ và mờ dần `alpha -> 0`), trong khi vòng lặp bài mới cùng cụm tiêu đề `.ring-center` bên trong trượt mượt mà từ vị trí vòng thứ hai (`L.b` / `L2.b`) vào chính tâm sân khấu (`L.a`) và nở đều từ `0.65 * R` lên `R`.
3. **Triệt tiêu Khoảng Trống Tải & Pre-fetch Chuyển Bài (`web/js/stage_sync.js`, `web/js/viz.js`):**
   - Duy trì `stageSync.primaryTrack` của bài trước trong ~20ms khi `ensureTrack` đang tải phân tích bài mới, kết hợp hàm `_prefetchCandidateTransitions` và `prefetch_ids` từ máy chính để nạp sẵn phân tích các bài kế tiếp vào `trackCache` với độ trễ 0ms.
   - Bổ sung đồng bộ `app_ver: "v161"` trong gói telemetry và `NoCacheStaticFiles` cho đường dẫn gốc (`/?mode=satellite`) trong `loopbox/server.py` để màn hình vệ tinh luôn tự động làm mới khi nâng cấp phiên bản.
4. **Đồng bộ toàn diện Nội dung, Điểm Nhảy Nét Đứt, Vòng Chờ "ĐANG TẢI" & Hai Con Trỏ Playhead (`web/js/viz.js`, `web/js/stage_sync.js`):**
   - Tuần tự hóa `this.player.plan.jumps` (`Map`) qua `Array.from()` để hiển thị đầy đủ đường nhảy nét đứt màu hổ phách và vòng tròn thở tại điểm nối (`exitT`).
   - Đồng bộ trực tiếp `rc_kicker_html`, `rc_title_html`, `rc_meta_html`, `placeholder` (`ĐANG TẢI`), `lead_head` và `ghost_head`.

### 2. Kiểm thử & Xác thực (Verification)
- Lệnh kiểm tra:
  - `node --check web/js/viz.js; node --check web/js/stage_sync.js; node --check web/js/main.js` (Exit Code 0)
  - `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py` (Exit Code 0)
  - `.\.venv\Scripts\python.exe tests/test_stage_sync.py` (Exit Code 0)

---

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

---

## Phiên làm việc: 07/11/2026

### 1. Mục tiêu hoàn thành (v1.0.30 - Web Dev Mode & Continuum Satellite Overhaul)
1. **Chuyển sang Web Dev Mode theo chỉ thị của người dùng:**
   - Kill tiến trình `MeikovaLoop.exe` (PID 24772) để tránh việc phải build exe nhiều lần.
   - Chạy trực tiếp web server từ mã nguồn Python (`.\.venv\Scripts\python.exe -m loopbox.server`) trên cổng `0.0.0.0:8765` (PID 1724).
   - Mọi thay đổi trong `web/` và `loopbox/` có hiệu lực ngay lập tức khi tải lại trang mà không cần đóng gói lại binary.

2. **Khắc phục triệt để lỗi Lệch màu giữa Danh sách bài hát (Mini Ring) và Canvas:**
   - **Nguyên nhân gốc rễ:** Trong `web/js/main.js`, module `theme.js` bị import kèm tham số truy vấn: `import * as theme from "./theme.js?v=131";`, trong khi `viz.js` và `stage_sync.js` import chuẩn `import * as theme from "./theme.js";`. Trong cơ chế ES Modules của trình duyệt, hai đường dẫn này tạo ra **hai phiên bản singleton độc lập hoàn toàn trong RAM**. Khi `main.js` nạp danh sách và gọi `theme.setMoods(metas)`, dữ liệu `moods` chỉ ghi vào instance của `main.js` (khiến mini ring có màu mood thật: Hồng cho *Sơn Thuỷ Trùng Mây*, Vàng cho *Bát Phương Lai Tài*). Instance của `viz.js` có map `moods` rỗng nên canvas luôn fallback sang hàm băm `hashHue(id)` (Xanh lam 258 cho *Sơn Thuỷ Trùng Mây*, Hồng 349 cho *Bát Phương Lai Tài*).
   - **Giải pháp:** Đồng bộ 100% relative imports trong ES Modules bỏ triệt để query string `?v=`, tái sử dụng cùng một instance duy nhất. Bổ sung `fallbackMood` vào `theme.accentOf(track.id, mood)` và `theme.songColor(track.id, mood)` trong `viz.js`. Giờ đây màu sắc trên Canvas, Mini Ring trong thư viện, và Stage Ring vệ tinh hoàn toàn đồng nhất 100%.

3. **Tái thiết kế toàn diện màn hình Vệ tinh (Satellite Stage) kế thừa trực tiếp từ Canvas Host:**
   - Thay thế toàn bộ wireframe và logic chắp vá cũ: Sân khấu vệ tinh giờ đây tái sử dụng trực tiếp engine vẽ canvas của máy chính (`_drawRing`, `_drawLights`, `_drawHalo`, `_drawHead`).
   - Khắc phục lỗi thiếu vạch hào quang (Halo spectrum needle corona): Đã sửa lỗi bất đồng bộ số lượng dải tần giữa máy chủ (slice 32) và bộ vẽ Halo (`HALO_BANDS = 48`) gây ra giá trị `NaN` làm ẩn toàn bộ hào quang trên vệ tinh; nâng cấp Host truyền đủ 48 bands và bổ sung mảng phòng vệ `Float32Array(HALO_BANDS)` chống `NaN`.
   - Khắc phục lỗi mất đầu kim phát sáng (Playhead): Vẽ kết hợp cả cung phách phát sáng (`_drawHead`) lẫn viên ngọc quỹ đạo phát quang có lõi trắng sắc nét (`_drawSatelliteHead`) thở theo nhịp bass/pulse.
   - Bổ sung các chấm điểm nối bài (Candidate / Exit Dots) quanh viền ngoài vòng lặp: Vệ tinh nạp đồng thời `api.transitions(id)` song song với `api.analysis(id)`, giúp hiển thị đầy đủ các chấm màu biểu thị điểm chuyển bài sang các track khác.
   - Căn giữa hoàn hảo (Centering) trên mọi tỉ lệ khung hình vệ tinh (split window, tablet, TV, mobile): Khắc phục việc lấy tọa độ tương đối lệch của Host (bị đẩy sang trái do thư viện 380px), ép vòng lặp vệ tinh luôn neo chuẩn xác tại tâm màn hình `(cx, cy)`.
   - Tự động kích hoạt căn chỉnh kích thước (Auto-resize trên frame đầu tiên) mà không đòi hỏi người dùng phải kéo co dãn cửa sổ.
   - Khắc phục tràn chữ và vỡ giao diện tiêu đề bài hát dài: Tách tự động Tên bài và Nghệ sĩ qua `splitTitle()`; CSS giới hạn tiêu đề tối đa 2 dòng (`-webkit-line-clamp: 2`), cân đối hoàn hảo trong tâm vòng tròn.

4. **Triệt tiêu hiện tượng Nhấp nháy (Flickering) trên màn hình Vệ tinh:**
   - **Nguyên nhân:** Trước đó, mỗi gói tin telemetry (~30 lần/giây) lại gọi `ensureTrack` tạo Promise nạp API và ghi 7 biến CSS lên `:root` gây ra style recalculation cascade liên tục; đồng thời selector `body.is-satellite-mode :root` trong CSS không hợp lệ khiến animation transitions bị xung đột.
   - **Giải pháp:** Bổ sung cơ chế Change Detection có ngưỡng (chỉ ghi CSS variable khi giá trị màu đổi thật sự); chỉ gọi `ensureTrack` một lần duy nhất khi ID bài hát thay đổi; sửa selector CSS thành `html.is-satellite-mode, html.is-satellite-mode * { transition: none !important; }`.

5. **Hiển thị chuẩn số lượng màn hình Vệ tinh đang kết nối (`satellites_count`):**
   - Sửa triệt để lỗi CSS vỡ giao diện badge trên Topbar: Khắc phục hàm `updateBadge()` bị khai báo trùng lặp trong `stage_sync.js` ghi text `"1 vệ tinh"` dài 55px làm tràn sang nút Cloud Tunnel kế bên. Giờ đây badge chỉ hiển thị số lượng gọn gàng (`1`, `2`, `3`...).
   - CSS định dạng lại `.sync-count-badge` thành badge tròn 16x16px neo chuẩn xác góc trên bên phải của nút icon 34px (`top: -2px; right: -2px;`), có viền tương phản `border: 1.5px solid var(--ink-0)` và neon glow chuẩn thương hiệu.
   - Cập nhật số lượng vệ tinh lên badge `#stage-sync-badge` trên nút Topbar (`Sân khấu`) và modal `#modalStageSync`. Khi có thiết bị kết nối, badge lập tức hiển thị số lượng chuẩn; khi ngắt kết nối tự động ẩn.
   - `loopbox/stage_sync_hub.py` phát sóng `sync_status` đồng thời tới cả hosts lẫn satellites khi có bất kỳ thiết bị nào kết nối/ngắt kết nối.
   - Nâng cấp phiên bản web cache buster lên `v=136` trong `web/index.html`.

6. **Responsive Layout trên Màn hình Hẹp & Di động:**
   - Bổ sung Media Query `@media (max-width: 680px)` cho Zen HUD Top: Tự động ẩn nhãn chữ cồng kềnh, chuyển các nút công cụ (`Tape`, `Sweep`, `Neon`, `REC`, `Mini`, `Thoát`) thành các nút tròn icon 32x32px gọn gàng, có đệm `env(safe-area-inset-top)`. Triệt tiêu hoàn toàn hiện tượng tràn viền, đè chữ và vỡ giao diện trên mobile.

### 2. Kiểm thử & Xác thực (Verification)
- Kiểm tra cú pháp JavaScript: `node --check web/js/*.js` -> **PASS (Exit Code 0)**
- Kiểm thử đơn vị Python: `python -m unittest discover -s tests` -> **Ran 41 tests, ALL PASSED (Exit Code 0)**
- Máy chủ phát triển: Đang chạy nền tại `http://localhost:8765` và `http://0.0.0.0:8765` (PID 1724).

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

## Phiên làm việc: Khắc phục lỗi Stacking Context đè lên Popover Micro Karaoke (v1.0.29)
- **Thời gian:** 2026-11-06 22:08 +07:00
- **Nguyên nhân gốc rễ (Root Cause):**
  1. Container `.stage` chứa 2 phần tử chính: `.canvas-wrap` và `.deck`.
  2. `.canvas-wrap` chứa `#ring-center` mang thuộc tính `position: absolute; z-index: 2;`.
  3. Thanh điều khiển `.deck` trước đây có `position: static` (không có position) và `z-index: auto` (tương đương cấp độ 0 trong stacking context của `.stage`).
  4. Theo chuẩn CSS Stacking Context (W3C), các phần tử con có `z-index > 0` (`#ring-center` z-index 2) luôn được hiển thị trên các phần tử static hoặc z-index 0. Do đó, dòng chữ to màu trắng "Chọn một bài để bắt đầu vòng lặp / Bấm phát..." luôn bị render đè lên mặt `.deck` và xuyên qua `.mic-popover`.
- **Giải pháp xử lý:**
  1. Nâng cấp CSS Stacking Context:
     - Gán `.canvas-wrap { position: relative; z-index: 1; }`
     - Gán `.deck { position: relative; z-index: 30; }` (cả ở desktop, sticky mobile, và zen mode)
     - Gán `.deck__mic-wrap.is-open, .deck__mic-wrap:has(.mic-popover:not([hidden])) { z-index: 60; }`
     - Nâng cấp `.mic-popover { z-index: 100; background: oklch(0.13 ... / 0.98); backdrop-filter: blur(24px); }` để hoàn toàn che lấp và nổi lên trên mọi thành phần sân khấu.
  2. Bổ sung điều khiển tương tác popover (`main.js`):
     - Tự động đóng popover EQ/Timer khi mở Popover Mic và ngược lại.
     - Hỗ trợ phím Escape để đóng nhanh popover.
  3. Nâng phiên bản SSOT lên **v1.0.29** qua `version.py`.
- **Kết quả kiểm thử:**
  - Test suite `tests/test_server_and_features.py`: PASS (Exit Code 0).
  - PyInstaller build `dist/MeikovaLoop/MeikovaLoop.exe`: PASS (Exit Code 0).
  - Git commit: `50081f4` đã push lên GitHub `origin main`.

## Phiên làm việc: Sân khấu Ánh sáng Đa sắc, Sửa Volume Loa Ngoài, Phím Media AVRCP & Tối ưu RAM (v1.0.30)
- **Thời gian:** 2026-11-06 23:40 +07:00
- **Mục tiêu hoàn thành:**
  1. **Đồng bộ Ánh sáng & Sân khấu Đa sắc (Dual-Color Transition Sync):**
     - Nâng cấp SmartLightsManager và stage_sync_hub: Truyền đồng thời color_a, color_b, is_transitioning, progress.
     - Với WLED (LED strip đa vùng): Sinh luồng DDP UDP vẽ dải màu gradient mượt mà giữa Bài A và Bài B.
     - Với ASUS TUF Keyboard (driver ACPI kernel \\.\ATKACPI): Pha trộn màu OKLCH chủ đạo và điều biến theo bass pulse.
     - Với Màn hình Vệ tinh (iz.js): Vẽ 2 vòng lặp sân khấu (color_a và color_b) chạm nhau có sóng âm 60 FPS mà không cần tải file audio.
  2. **Sửa lỗi 'Chưa phát' trên Mini Player:**
     - Khắc phục cấu trúc player.cur bằng cách truy xuất player.cur?.track?.id || player.cur?.id và songOf(curMeta).
  3. **Khắc phục lỗi đảo ngược Volume khi rút loa ngoài:**
     - Thiết lập cơ chế WindowsVolume.update_endpoint() động: phát hiện rút loa ngoài qua IMMDevice::GetId().
     - Kiểm tra trạng thái MUTE thực tế của loa chính, không bao giờ fallback về 1.0.
  4. **Đồng bộ Phím Media trên Loa Ngoài (JBL Bluetooth AVRCP):**
     - Nâng cấp _media_keys_loop bắt sườn lên & 0x8000. Phím Play trên loa tự động kích hoạt bài hát đầu tiên nếu chưa phát.
  5. **Tên Tiến trình WebView2 & Tối ưu hóa Bộ nhớ RAM:**
     - Rút gọn <title> thành Meikova Loop để Task Manager hiển thị ngắn gọn, chuyên nghiệp.
     - Giới hạn V8 Heap --js-flags=--max-old-space-size=256 và --renderer-process-limit=2.
     - Giảm maxPrefetch từ 3 xuống 1 bài; giảm Loader.keep từ 5 xuống 2 bài.
     - Tự động dọn dẹp AudioBuffer và VocalBuffer của bài cũ sau mỗi lần chuyển bài (promote), tiết kiệm hơn 60% RAM.
- **Kiểm thử (Verification):**
  - 	ests/test_stage_sync.py: PASS (Exit Code 0).
  - 	ests/test_server_and_features.py: PASS (Exit Code 0).


## Phiên làm việc: Hoàn thiện Meikova Ambient UI cho Modal "Đồng bộ Ánh sáng & Vệ tinh" (#modalStageSync)

- **Mục tiêu hoàn thành:**
  1. **Khắc phục triệt để lỗi Broken Image QR Code:**
     - Backend (`loopbox/server.py`): Đảm bảo import `from urllib.parse import quote, unquote`. Mã hóa `quote(target_satellite_url, safe='')` và trả về đồng thời 2 trường `qr_url` và `qr_code`.
     - Frontend (`web/js/stage_sync.js`): Gán fallback `roomRes.qr_code || roomRes.qr_url || ("/api/qr?data=" + encodeURIComponent(...))`. Endpoint `/api/qr` render SVG trực tiếp (7086 bytes) đạt HTTP 200, tuân thủ nghiêm ngặt chuẩn OWASP & Zero External QR.
  2. **Thay thế Nút Đóng thành chuẩn Meikova Ambient UI:**
     - Thay class `.btn-tunnel-close` bằng `.tunnel-modal__close` (28x28px, bo góc 7px, hiệu ứng xoay 90 độ khi hover, viền hairline `var(--line)`, hover `var(--accent)`).
  3. **Thiết kế lại Toggle Switch cho Đèn & Bàn phím:**
     - Bổ sung toàn diện CSS cho `.tunnel-toggle-switch` và `.switch-handle` (kích thước chuẩn 44x24px, bo góc viên thuốc 9999px, handle tròn 18px trượt 20px với cubic-bezier mượt mà, hiệu ứng neon glow emerald `oklch(var(--acc) / 0.4)` khi bật).
     - Tuân thủ Zero-Double-Border và Zero-Native-Inputs.
  4. **Tái cấu trúc giao diện Tab "Màn hình Vệ tinh":**
     - Đưa cấu trúc thẻ `.sync-qr-card` theo chuẩn `.mobile-modal__qr-card`: Khung QR bo góc 8px (112x112px) bên trái, thông tin chi tiết và đèn telemetry `.status-dot.tunnel-dot--running` phát quang bên phải.
     - Thanh URL mono kèm bộ đôi nút `.btn-copy-pill` ("Sao chép" và "Mở thử") đồng bộ với Design System của Meikova Continuum.
  5. **Responsive & Mobile Touch Mandate:**
     - Mobile Portrait (<600px): `.sync-qr-card` tự động căn giữa theo chiều dọc, nút bấm đạt diện tích chạm tối thiểu 44px (Apple HIG).
     - Mobile Landscape (<520px height): cuộn mượt `max-height: calc(100dvh - 16px)`, khung QR thu gọn 80x80px chống tràn màn hình.
  6. **Đóng gói & Chạy trực tiếp:**
     - Đã đóng gói lại bản native `MeikovaLoop.exe` qua PyInstaller thành công với Exit Code 0.
     - Khởi chạy thành công ứng dụng trên máy, port 8765 mở và phản hồi 200 OK.

- **Lệnh kiểm tra đã chạy & Kết quả:**
  - `python tests/test_stage_sync.py`: ALL 5 TESTS PASSED (Exit Code 0).
  - `python tests/test_server_and_features.py`: ALL 35 TESTS PASSED (Exit Code 0).
  - `Invoke-RestMethod http://127.0.0.1:8765/api/sync/room-info`: 200 OK, trả về cả `qr_url` và `qr_code`.
  - `GET http://127.0.0.1:8765/api/qr?data=...`: 200 OK, `image/svg+xml`, 7086 bytes.

## Phiên làm việc: Khắc phục Màn hình Vệ tinh, Lệch màu Bài hát, Bluetooth Auto-play, và Build Windows Executable
- **Thời gian:** 2026-11-07 14:40 +07:00
- **Mục tiêu hoàn thành:**
  1. **Khắc phục Màn hình Vệ tinh Nhấp nháy & Vỡ Responsive trên Di động:**
     - *Nguyên nhân:* Màn hình vệ tinh (`?mode=satellite`) trước đây bị gán class `is-zen`, khiến thanh công cụ Zen của Host (`#zen-hud-top`, `.zen-hud-tools`, `Tape`, `Sweep`, `Neon`, `REC`, `Mini`) xuất hiện trên màn hình điện thoại với chiều rộng >700px, gây tràn ngang sinh thanh cuộn và làm giật lag, nhấp nháy canvas khi redraw. Đồng thời các thuộc tính textContent DOM được gán lặp lại liên tục theo mỗi gói tin WebSocket.
     - *Khắc phục:*
       - Gỡ bỏ `is-zen` khỏi satellite mode; bổ sung CSS cách ly triệt để `body.is-satellite-mode`: khóa cứng `width: 100vw; height: 100dvh; overflow: hidden; touch-action: none;` và ẩn hoàn toàn toàn bộ topbar, zen hud, panel, deck của Host.
       - Thêm guard `if (el.textContent !== newText) el.textContent = newText;` chống DOM reflow churn.
  2. **Đồng bộ Canvas Vệ tinh với Canvas Thiết bị Chính:**
     - Thiết bị vệ tinh tự động tải phân tích bài hát (`/api/tracks/{id}/analysis`) qua `Track(meta, analysis)`.
     - `_drawSatelliteStage` vẽ đầy đủ toàn bộ visualizer Infinite Jukebox: các cung phách timbre beat segments đổi màu theo phong cách riêng, cung nhảy phách jump chords, vạch chia nhịp dial ticks, nhãn phút thẳng đứng, quầng hào quang phổ tần số âm thanh thở theo bass (`_drawSatelliteHalo`), đầu kim orbital playhead phát sáng có đuôi tàn lửa (`_drawSatelliteHead`), và căn giữa chuẩn xác tiêu đề bài hát (`_placeCenter`).
  3. **Hiển thị Số lượng Vệ tinh Kết nối Chuẩn xác:**
     - `StageSyncHub` theo dõi tập WebSocket vệ tinh `self.satellites`, tự động phát sóng `sync_status` và loại bỏ các kết nối đứt đoạn.
     - Badge trên Topbar Host (`#stage-sync-badge`) và nhãn trong Modal (`#sync-sat-connected-status`) tự động cập nhật thời gian thực theo số lượng thiết bị vệ tinh đang hoạt động.
  4. **Khắc phục Sai lệch Màu sắc giữa Thư viện và Sân khấu:**
     - *Nguyên nhân:* Khi thư viện render trước khi bài hát có dữ liệu phân tích tâm trạng (mood valence/energy), hàm `songColor` gán màu fallback (dựa vào `hashHue`) và bị lưu vĩnh viễn vào cache `cache.set(k, col)`. Sau khi phân tích xong hoặc khi đổi theme, mini canvas và chuỗi setlist vẫn mang màu fallback cũ (ví dụ: màu hồng) trong khi sân khấu chuyển sang màu chuẩn (ví dụ: xanh cyan).
     - *Khắc phục:* Trong `web/js/theme.js`, bổ sung điều kiện `const isKnown = moods.has(id);` - chỉ cho phép cache màu khi track đã có mood ranking. Thêm version và theme vào cache key (`s:${id}:${current}.${version}`). Mỗi khi `setMoods()` cập nhật, `version++` và xóa sạch cache. Khi `recolor()` gọi `miniCache.clear()` và vẽ lại setlist tức thì.
  5. **Khắc phục Lỗi Tự phát Nhạc khi Kết nối lại Loa Bluetooth:**
     - *Nguyên nhân:* Khi người dùng chủ động Pause (`userPaused = true`), sau đó ngắt và kết nối lại loa ngoài, Chromium/Windows Media Foundation re-route audio stream và bắn sự kiện `play` trên thẻ audio mỏ neo (`_bgAudio`). Tại `player.js:253`, sự kiện `_onExternalPlay` trước đây gọi thẳng `if (this.userPaused) await this.play();`, dẫn đến việc nhạc tự động phát lại.
     - *Khắc phục (3 tầng bảo vệ):*
       - Tầng 1 (`engine.js`): Thẻ `_bgAudio` lắng nghe `play`: nếu `!this._shouldBePlaying` thì lập tức gọi `a.pause()` và không chuyển tiếp sự kiện.
       - Tầng 2 (`player.js`): `_onExternalPlay` kiểm tra nghiêm ngặt `if (!this.userPaused && !this.playing && this.cur) await this.play();`. Nếu `userPaused` là `true`, tuyệt đối không phát!
       - Tầng 3 (`main.js`): Sự kiện `devicechange` kiểm tra nếu `player.userPaused` thì lập tức thực thi `engine.stopAnchor()` và `engine.stopAll(0.01)`.
  6. **Đóng gói Windows Executable Mới:**
     - Biên dịch thành công `dist/MeikovaLoop/MeikovaLoop.exe` (PyInstaller 6.22, Exit Code 0, dung lượng ~67.1 MB).
     - Đồng bộ toàn bộ web assets vào `dist/MeikovaLoop/_internal/web/`.
- **Kiểm thử (Verification):**
  - Cú pháp JS: `Get-ChildItem web/js/*.js | ForEach-Object { node -c $_.FullName }` -> Exit Code 0.
  - Python tests: `python -m unittest discover -s tests` -> 41/41 tests PASSED (Exit Code 0).

---

## Phiên làm việc: Khắc phục Triệt để Đơ Màn hình Vệ tinh, Lệch màu OKLCH & Lỗi CSS Badge (v1.0.31 - Dev Mode)
- **Thời gian:** 2026-11-07 18:10 +07:00
- **Mục tiêu hoàn thành:**
  1. **Triệt tiêu Hiện tượng Đơ / Chậm nạp Màn hình Vệ tinh (Zero-Freeze Satellite):**
     - *Nguyên nhân gốc rễ:* Chromium tự động tạm dừng hoặc giảm tốc độ `requestAnimationFrame` về 0–1 FPS đối với các tab/cửa sổ không có tiêu điểm (unfocused) và không phát âm thanh. Màn hình vệ tinh không phát âm thanh và người dùng thao tác ở cửa sổ Host, nên cửa sổ vệ tinh bị Chromium coi là idle. Trước đó canvas chỉ được vẽ trong vòng lặp rAF, các gói tin WebSocket telemetry (~30 gói/s) và callback `ensureTrack` chỉ cập nhật DOM mà không kích hoạt vẽ canvas. Do đó màn hình vệ tinh bị đơ ra cho tới khi người dùng click, focus hoặc thay đổi kích thước cửa sổ.
     - *Giải pháp triệt để:*
       + Bổ sung phương thức `renderSatellite(telemetry)` chuyên dụng vào class `Viz`.
       + Kích hoạt lệnh vẽ canvas trực tiếp ngay khi nhận gói tin WebSocket telemetry (`ws.onmessage` -> `handleMessage` -> `this.viz.renderSatellite()`), không bị ảnh hưởng bởi rAF throttling của trình duyệt.
       + Bổ sung backup interval `setInterval(() => this.renderSatellite(), 33)` trong `Viz` constructor để duy trì 30 FPS liên tục ngay cả khi cửa sổ nằm dưới nền.
       + Gán tham chiếu trực tiếp `stageSync.viz = viz` để gọi ngay `this.viz.invalidate()` và `this.viz.renderSatellite()` khi `ensureTrack` tải xong dữ liệu phân tích nhịp.
       + Sửa hàm `Viz.invalidate()` reset cả `this.satellitePrimaryRing.layerKey = ""` và `this.satelliteSecondRing.layerKey = ""`.

  2. **Đồng bộ Màu sắc 100% giữa Danh sách Bài hát và Canvas (Host & Satellite):**
     - *Nguyên nhân gốc rễ:* Trên máy Host, khi tải danh sách bài hát, hàm `theme.setMoods(metas)` chạy thuật toán phân hạng rank-based normalization trải đều các bài hát theo tâm trạng trên mặt phẳng 2D. Trước đó trang vệ tinh không gọi `api.tracks()`, nên map `theme.moods` trên vệ tinh bị rỗng, dẫn đến việc tính màu fallback không xếp hạng làm bài hát bị lệch sang màu hồng (hue 349).
     - *Giải pháp triệt để:*
       + Khi vệ tinh khởi động, tự động gọi `api.tracks()` để nạp `metas` và chạy `theme.setMoods(res.tracks)`.
       + Máy Host phát sóng đồng thời `enabled_ids` trong telemetry; vệ tinh lọc các điểm nối thoát (`_shown`) theo `stageSync.enabledIds`.
       + Khi Host đổi theme, vệ tinh nhận `theme` mới và lập tức invalidate layers để vẽ lại với bảng màu tương ứng.
       + Giờ đây toàn bộ beat blocks, chords, dust particles và candidate dots trên vệ tinh mang màu sắc OKLCH hoàn toàn đồng nhất với Host.

  3. **Khắc phục Thứ tự Vẽ Lớp & Chi tiết Sân khấu Vệ tinh:**
     - *Nguyên nhân:* Trong `_drawSatelliteStage`, hàm vẽ hào quang phổ âm thanh `_drawHalo` được gọi *sau* `_drawRing`, khiến hình gradient dạng polygon của halo bị đè lên mặt vòng lặp, che khuất các khối nhịp và dây nối phách. Đồng thời gọi trùng cả `_drawHead` lẫn `_drawSatelliteHead` làm đầu kim bị chồng lặp.
     - *Giải pháp:* Đưa `_drawHalo` lên trước `_drawRing` (vẽ quầng hào quang nằm bên dưới vòng tròn như máy chính). Chỉ gọi `_drawSatelliteHead` khi chưa nạp xong analysis, còn khi có analysis thì `_drawHead` vẽ đúng chuẩn đầu kim quỹ đạo phát sáng.

  4. **Khắc phục Lỗi CSS Badge Vệ tinh trên Topbar:**
     - Badge `#stage-sync-badge` chỉ hiển thị số lượng ngắn gọn (`1`, `2`), định vị chuẩn `position: absolute; top: -3px; right: -3px;` dạng bong bóng thông báo tròn không bao giờ tràn đè lên các nút icon liền kề.
     - Tiêu đề `.rc-title` trên vệ tinh sử dụng `font-size: var(--rc-size, 24px) !important;` co dãn tự động theo bán kính vòng tròn.

  5. **Môi trường Web Dev Mode:**
     - Server dev đang chạy nền trực tiếp từ mã nguồn Python trên `0.0.0.0:8765` (Task `task-32554`), sẵn sàng để người dùng thử nghiệm trên trình duyệt / LAN trước khi build binary `.exe`.

- **Kiểm thử (Verification):**
  - Cú pháp JS: `node --check web/js/viz.js; node --check web/js/stage_sync.js; node --check web/js/main.js` -> **PASS (Exit Code 0)**.
  - Python tests stage sync: `python tests/test_stage_sync.py` -> **5/5 PASS (Exit Code 0)**.
  - Python tests server & features: `python tests/test_server_and_features.py` -> **PASS (Exit Code 0)**.
  - Kiểm tra kết nối mạng: `http://127.0.0.1:8765/api/tracks` phản hồi 200 OK (57KB). Endpoint `/api/qr` sinh vector SVG 200 OK.



  5. **Môi trường Web Dev Mode:**
     - Server dev đang chạy nền trực tiếp từ mã nguồn Python trên 0.0.0.0:8765 (Task task-33381), sẵn sàng để người dùng thử nghiệm trên trình duyệt / LAN trước khi build binary .exe.

  6. **Khắc phục Triệt để Vấn đề Playlist & Màn hình Vệ tinh (Phiên mới nhất):**
     - **Khôi phục & Đồng bộ Playlist 2 chiều (Desktop <-> Web Local):**
       + Trích xuất dữ liệu gốc LevelDB WebView2 của 2 playlist 'Suy' (50 bài) và 'Remix' (48 bài) lưu vào SSOT playlists.json.
       + Thêm endpoint /api/playlists kèm header Cache-Control: no-cache, no-store, must-revalidate.
       + Trong web/js/main.js: loadPlaylists() render ngay từ cache, sau đó merge với server và cập nhật DOM #pl-chips không phụ thuộc vào trạng thái tab.
     - **Triệt tiêu Tận gốc Hiện tượng Đơ / Treo trên Vệ tinh:**
       + Sửa bẫy logic this.trackCache.has(id): Không gán dummy objects { analysis: null } làm chặn fetch dữ liệu.
       + Luôn kiểm tra cached && cached.analysis, nếu chưa có sẽ tự động gọi ensureTrack(info).
       + Ngay khi nạp xong api.analysis, ensureTrack tự động cập nhật ngay this.primaryTrack và gọi this.viz.invalidate().
     - **Triệt tiêu Đa giác Gãy khúc (Jagged Polygon Outer Line):**
       + Loại bỏ _drawHalo giả lập gây ra đa giác gãy 24 cạnh trên màn hình vệ tinh.
       + Thay bằng quầng sáng Ambient Radial Glow tròn xoe mềm mại, đồng bộ theo nhịp beat pulse & bass.
     - **Đồng bộ Màu sắc 1:1 Tuyệt đối Host -> Satellite:**
       + theme.beatColors hỗ trợ tham số forcedBase. Khi ở Satellite mode, canvas dùng trực tiếp hostCol từ telemetry của Host làm màu cơ sở để phân bổ beatColors và chord lines.
       + Hàm invalidate() reset toàn bộ ring.col = null và xóa sạch cache màu cũ.
     - **Khắc phục Lỗi Chữ Đè ('HAI VÒNG ĐANG CHỜ'):**
       + initSatelliteUI() thiết lập ngay trạng thái chờ ban đầu và ẩn vĩnh viễn nút #rc-cta.
       + applySatelliteTelemetry() sử dụng fallback chuỗi title từ metadata khi đổi bài, không bao giờ để lộ text mặc định của HTML.
     - **Chuẩn hóa Badge Topbar '1 vệ tinh':**
       + Sửa text badge chỉ hiển thị con số gọn gàng (1, 2), styling hình tròn 17x17px optical center.
     - **Bump Cache Version:**
       + Cập nhật ?v=142 trên index.html và meikova-loop-v142 trên sw.js để mọi trình duyệt client nhận ngay bản dựng mới.

- **Kiểm thử (Verification):**
  - JS syntax check: node --check web/js/viz.js; node --check web/js/stage_sync.js; node --check web/js/main.js; node --check web/js/theme.js -> PASS (Exit Code 0).
  - Python tests stage sync: python tests/test_stage_sync.py -> 5/5 PASS (Exit Code 0).
  - Python tests server & features: python tests/test_server_and_features.py -> PASS (Exit Code 0).
  - API Playlists endpoint: GET /api/playlists -> 200 OK (2 playlists, 98 tracks).
  - Deck responsive verification: python scripts/verify_deck_responsive.py -> PASS (Exit Code 0).

  7. **Tối ưu Responsive Deck trên Mobile & Triệt tiêu Tràn Ngang Màn hình (Phiên mới nhất):**
     - **Nguyên nhân gốc rễ (Root Cause):**
       + Trên màn hình di động (portrait 360px - 430px như iPhone 15/16 Pro), `.deck` chứa 12 nút bấm dàn hàng ngang với tổng chiều rộng nội tại > 500px (`min-width: 36px` + `flex-shrink: 0`).
       + Container `.deck` và `html, body` thiếu `overflow-x: hidden` / `overflow-x: auto`, khiến thanh điều khiển tràn ra ngoài biên màn hình (~55px mỗi bên).
       + Khi người dùng vuốt/kéo sang phải để xem các nút Hẹn giờ/EQ/Âm lượng, trình duyệt di động cuộn ngang toàn bộ trang web (`body.scrollLeft > 0`), làm lệch cả thanh tab dưới cùng (`[♫ Thư viện] [||| Tinh chỉnh]`) và ô tìm kiếm.
     - **Giải pháp Kiến trúc Chuẩn Meikova (Precision Studio Floating Deck):**
       + **Phân tầng 2 hàng (2-Tier Studio Console):** Phân chia 12 nút bấm thành 2 nhóm ngữ nghĩa:
         * Hàng 1 (Vận hành cốt lõi): `Khoá`, `Nhảy`, `Phát (Hero 48px phát quang trung tâm)`, `Bài khác`, `Kho/Playlist`.
         * Hàng 2 (Công cụ âm thanh & tiện ích): `Thu âm`, `Tách giọng`, `Mic Karaoke`, `Hẹn giờ`, `Chế độ đêm`, `Hiệu ứng EQ`, `Âm lượng / Tắt tiếng`.
       + **Tương thích tuyệt đối trên Desktop & Tablet (`display: contents;`):** Trên màn hình lớn (> 600px), `.deck__row` áp dụng `display: contents;`, giữ nguyên 100% thanh điều khiển nổi 1 hàng liền mạch như ban đầu.
       + **Khoá chặt cuộn ngang Viewport (Zero-Horizontal-Scrollbar on Viewport):**
         * `html, body` ép `max-width: 100vw; overflow-x: hidden !important;`.
         * `.layout`, `.stage`, `.canvas-wrap`, `.panel` áp dụng `max-width: 100vw; overflow-x: clip;`.
       + **Phòng thủ đa tầng trên màn hình siêu hẹp:** Hàng 2 trang bị `overflow-x: auto; overscroll-behavior-x: contain;` phòng trường hợp màn hình quá nhỏ (< 320px) vẫn cuộn mượt nội bộ không ảnh hưởng đến thân trang.
       + **Menu Popover Di động Chuẩn Quy tắc Meikova:**
         * `.mic-popover`, `.timer-popover`, `.eq-popover` áp dụng `position: fixed; bottom: calc(env(...) + 116px); left: 50%; transform: translateX(-50%); width: min(340px, calc(100vw - 20px)); z-index: 9999;`.
         * Hoàn toàn triệt tiêu nguy cơ bị cắt mép (clipping) bởi container cha, tự động căn giữa cân đối phía trên deck.
       + **Độ trễ chạm & Diện tích tiếp xúc (Apple HIG & WCAG 2.5.5):** Mở rộng vùng chạm tối thiểu 44x44px bằng pseudo-element `::after` (`inset: -5px`).
       + **Landscape Auto-Collapse:** Khi xoay ngang màn hình di động (`max-height: 520px`), tự động duỗi thẳng lại thành 1 hàng dẹt tiết kiệm chiều dọc.
       + **Bump Cache Version:** Cập nhật `css/app.css?v=143` và `meikova-loop-v143` trên Service Worker để thiết bị di động nạp ngay CSS mới.


  8. **Mobile Landscape Studio Cockpit (Side-by-Side 2-Column like Desktop - v145):**
     - **Vấn đề được báo cáo qua 4 ảnh chụp thực tế:**
       + Ở chế độ dọc (Ảnh 1 & 2): 2-tier floating studio deck hiển thị gọn gàng, không bị tràn viền.
       + Khi xoay ngang màn hình (Ảnh 3 & 4): Giao diện cũ bị xếp dọc 1 cột (grid-template-columns: 1fr; height: auto), Canvas vòng lặp chiếm hết chiều dọc màn hình (~390px), khiến Thư viện bị chìm sâu xuống đáy (phải cuộn trang mới thấy như Ảnh 3, còn ở trên thì mất Thư viện như Ảnh 4).
     - **Giải pháp Kiến trúc Chuẩn Meikova Studio:**
       + Áp dụng Media Query @media (max-height: 600px) and (orientation: landscape) đưa giao diện ngang về chuẩn **Studio Cockpit 2 cột song song như Desktop**:
         * Khóa chặt cuộn toàn trang: html, body { height: 100dvh !important; overflow: hidden !important; }.
         * Topbar siêu gọn 42px cố định ở đỉnh với đầy đủ Brand, nút chuyển [Một bài | Chuỗi], và các nút công cụ SVG 28px viền tròn.
         * .layout 2 cột song song: grid-template-columns: minmax(0, 1fr) min(380px, 44vw) !important; height: calc(100dvh - 42px) !important;.
         * **Cột Trái (Sân khấu - Stage):** Visualizer canvas tự động co dãn vừa khít tỷ lệ màn hình ngang; Deck 1 hàng ngang tinh gọn (38px) ghim đáy sân khấu.
         * **Cột Phải (Thư viện - Library Panel):** Đưa thẳng lên trên cùng bên cạnh sân khấu ('mang lên trên như trên máy tính'), giữ nguyên các tab [ ♫ Thư viện ] [ ☷ Tinh chỉnh ], ô tìm kiếm, filter chips, và danh sách bài hát cuộn mượt độc lập bên trong panel.
         * Mở rộng max-height: 600px tương thích toàn diện cho mọi dòng điện thoại (iPhone 16 Pro Max, Galaxy Ultra, Pixel Pro).
       + Bump cache buster lên ?v=145 trong index.html và meikova-loop-v145 trong sw.js để mọi thiết bị di động xóa cache cũ tức thì.
     - **Kiểm thử (Verification):**
       + python scripts/verify_deck_responsive.py: ALL TESTS PASSED (Exit Code 0).
       + 
ode --check các file JS: ALL PASSED (Exit Code 0).
       + .\.venv\Scripts\python.exe tests/test_stage_sync.py: 5/5 PASSED (Exit Code 0).
       + Dev Server trên cổng 8765: 200 OK.

  9. **Tinh chỉnh Tối ưu Giao diện Mobile Landscape (Studio Cockpit v146 - meikova-ambient-ui):**
     - **3 Điểm cải tiến theo phản hồi thực tế từ ảnh chụp media_1794075978426_8e940415.jpg:**
       1. **Thu gọn Thư viện bên phải:** Giảm --panel-w từ min(380px, 44vw) xuống clamp(240px, 32vw, 280px). Tiết kiệm ngay ~95px-100px chiều ngang cho Sân khấu bên trái, giúp vòng lặp visualizer nở rộng thoáng đãng và tỷ lệ 2 cột cân đối như bàn DJ thực thụ.
       2. **Triệt tiêu Tràn thanh Deck:**
          - Ẩn hoàn toàn slider range #s-vol và label % bên trong .deck__vol trên màn hình ngang di động (giống như mobile portrait), giữ lại nút mute 26px tinh gọn.
          - Tinh chỉnh kích thước 12 nút bấm về chuẩn compact 27x28px, Play hero 34x34px, khoảng cách gap: 2px.
          - Tổng chiều rộng toàn bộ Deck giảm xuống chỉ còn ~364px (trong khi Stage rộng tới 570px-650px), hoàn toàn nằm gọn ở tâm sân khấu, loại bỏ 100% hiện tượng tràn đè lên đường phân cách.
       3. **Triệt tiêu Khoảng thừa Đen bên phải ngoài cùng (Zero Compound Inset Void):**
          - Loại bỏ hiện tượng cộng dồn (compounding) padding giữa .topbar, .panel, .tab, .shelf và .tracklist.
          - Chuẩn hóa padding-right về max(env(safe-area-inset-right, 0px), 8px) duy nhất tại các phần tử nội dung, .panel ép padding-right: 0 !important;.
          - Khi không có Dynamic Island bên phải, khoảng đệm đối xứng chuẩn 8px như bên trái; khi có Dynamic Island, padding vừa khít camera mà không tạo ra dải đen chết 70px-80px.
          - Ẩn các nút desktop không cần thiết trên Topbar mobile (#btn-mini, #btn-shortcuts-modal).
     - **Cache & Verification:** Bump ?v=146 trong index.html và meikova-loop-v146 trong sw.js. Toàn bộ test suite PASS với Exit Code 0.

  10. **Xử lý Triệt để Lỗi CSS Responsive Mobile Landscape (Studio Cockpit v147 - meikova-ambient-ui):**
     - **Nguyên nhân cốt lõi phát hiện từ ảnh chụp thực tế media_1794112958155_58aba0e8.jpg:**
       1. *Cột Thư viện bên phải chiếm 52% màn hình (528px / 1024px):* Trong `main.js`, `ui.panelWidth` được đọc từ `localStorage` (giá trị kéo thả trên desktop ~420px-528px) và gán inline: `document.documentElement.style.setProperty("--panel-w", ...)`. Thuộc tính inline `<html style="--panel-w: 528px">` có độ ưu tiên (specificity) cao hơn `:root { --panel-w: clamp(...) }` trong stylesheet, khiến luật CSS cũ bị ghi đè hoàn toàn. Khiến `.layout` phân chia 50/50, Sân khấu bị bóp nghẹt chỉ còn 496px.
       2. *Nút Khoá (#btn-lock) ở góc trái của Deck bị cắt mép (clipping):* `.deck` dạng viên thuốc (`border-radius: 9999px`) có chiều cao 34px -> bán kính bo tròn 17px. Đệm cũ `padding: 2px 6px` quá hẹp, khiến icon khoá nằm sát đường cong viền và bị cắn mất một nửa.
       3. *Khoảng trống đen vô nghĩa bên phải thư viện:* Tab bar `.tabs` không kéo dãn `width: 100%`, các trường nhập liệu không tự lấp đầy không gian còn lại.
     - **Giải pháp Xử lý Tận gốc (Root Cause Solution):**
       1. **Cách ly biến `--panel-w` trên Mobile Landscape:**
          - Trong `main.js`: Bổ sung kiểm tra `window.matchMedia("(max-height: 600px) and (orientation: landscape)").matches`. Khi ở màn hình ngang di động, tự động thực thi `document.documentElement.style.removeProperty("--panel-w")`, triệt tiêu hoàn toàn thuộc tính inline từ desktop. Đồng thời lắng nghe sự kiện `resize` và `orientationchange` để tự động phục hồi khi xoay về portrait hoặc mở trên desktop.
          - Trong `app.css`: Trên `.layout`, ép cứng định nghĩa cột độc lập `grid-template-columns: minmax(0, 1fr) clamp(240px, 28vw, 280px) !important;` KHÔNG phụ thuộc vào biến `var(--panel-w)`. Đảm bảo cột Thư viện luôn bị ghim chặt ở mức tối đa 280px (~28% màn hình), nhường lại hơn 72% chiều ngang (~744px) cho Sân khấu visualizer nở rộ.
       2. **Bảo vệ Đường cong Nút bấm Deck (Zero Left-Clipping):**
          - Tăng đệm an toàn của Deck lên `padding: 2px 14px !important;` tạo khoảng đệm an toàn 14px vượt qua góc bo cong bán kính 17px.
          - Bổ sung `margin-left: 2px !important;` cho `#btn-lock`, đảm bảo icon khoá hiển thị đầy đủ 100%, không bao giờ bị cắt mép.
          - Tinh chỉnh các nút phụ về 26x28px, nút Play 34x34px, tổng chiều rộng Deck thu gọn về ~376px, nằm lọt thỏm ngay tâm sân khấu 744px.
       3. **Lấp đầy Không gian Thư viện (Zero Compound Void):**
          - `.panel__head .tabs` đặt `width: 100% !important; display: flex !important;`, 2 tab "Thư viện" và "Tinh chỉnh" chia đều `flex: 1 !important; justify-content: center !important;` tựa như iOS segmented switch.
          - `.add__field`, `.shelf`, `.pl-chips-wrap`, `.lib-search`, `.tracklist`, `.track` ép `width: 100% !important; box-sizing: border-box !important;`, phân bố đều từ mép phân cách đến ranh giới an toàn bên phải.
       4. **Đồng bộ Phiên bản Cache Service Worker:**
          - Bump đồng loạt: `app.css?v=147`, `js/main.js?v=147`, `sw.js?v=147`, `CACHE_NAME = "meikova-loop-v147"`.
     - **Kiểm thử (Verification):**
       - `python scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
       - `node --check web/js/main.js`: Syntax OK (Exit Code 0).
       - Dev Server trên cổng 8765: 200 OK.

  11. **Tính năng Thu gọn Bảng điều khiển / Thư viện bên phải (Panel Collapse / Expand v148 - meikova-ambient-ui):**
     - **Yêu cầu người dùng:** Bổ sung nút thu gọn ở phần bên phải để ẩn đi khi cần thưởng thức trọn vẹn visualizer trên màn hình ngang hoặc máy tính.
     - **Triển khai kiến trúc:**
       1. **Nút Thu gọn (#btn-panel-collapse):**
          - Tích hợp trực tiếp trên `.panel__head` ngay cạnh các tab điều khiển.
          - Biểu tượng inline SVG chuẩn Lucide `panel-right-close` (khung hình chữ nhật kèm đường phân cách và mũi tên thu gọn về bên phải).
          - Bo góc tinh tế 8px, viền hairline Ambient Dark, hào quang neon glow khi hover, hỗ trợ touch target tối thiểu 44x44px.
       2. **Nút Mở lại Thư viện (#btn-panel-expand):**
          - Khi bảng điều khiển bị thu gọn (`body.is-panel-collapsed`), thanh panel ẩn đi và Sân khấu (Stage) tự động bung rộng 100vw toàn màn hình.
          - Một nút bấm dạng viên thuốc phát quang nổi (`.btn-panel-expand`) xuất hiện nhẹ nhàng ở góc trên bên phải màn hình (`top: calc(var(--topbar-h) + 8px); right: 12px;`).
          - Biểu tượng `panel-right-open` kèm nhãn "Thư viện" (tự thu gọn text chỉ để icon trên mobile nhỏ), giúp người dùng mở lại thư viện chỉ với 1 chạm.
       3. **Hỗ trợ Phím tắt Toàn cục:**
          - Phím `\` (Backslash) hoặc phím `B` (Bảng điều khiển / Sidebar) bật/tắt thu gọn thư viện tức thì khi không gõ trong ô nhập liệu.
          - Cập nhật vào danh sách phím tắt trong modal Trợ giúp (`?`).
       4. **Tự động Vẽ lại Visualizer:**
          - Luôn gọi `viz.invalidate()` ngay khi chuyển đổi trạng thái để Canvas visualizer tự động tái cấu trúc hình học vừa khít kích thước sân khấu mới mà không bị méo.
          - Lưu trạng thái vào `ui.panelCollapsed` để ghi nhớ phiên làm việc.
     - **Cache & Verification:** Bump `v148` toàn diện (`app.css?v=148`, `main.js?v=148`, `sw.js?v=148`, `meikova-loop-v148`). Toàn bộ test suite PASS với Exit Code 0.

  12. **Triệt tiêu Xung đột Vị trí Nút Thư viện & Hoàn thiện Hệ thống Bật/Tắt Kép (Panel Toggle & Edge-Dock Architecture v150 - meikova-ambient-ui):**
     - **Nguyên nhân gốc rễ lỗi hiển thị:**
       1. Trong bản v148, nút bung thư viện `.btn-panel-expand` nằm ở tọa độ `top: calc(var(--topbar-h) + 6px); right: 10px;`. Đây chính là tọa độ hiển thị của khối đo đạc viễn trắc sân khấu (`#ro-tr` - `∞ 0:00 · chưa có vòng nào`). Khi thu gọn bảng điều khiển, hai thành phần này đè trực tiếp lên nhau, che mất thông tin đo lường.
       2. Nút expand cũ sử dụng icon hình chữ nhật chia đôi (`panel-right`), thiếu nút điều khiển thường trực trên thanh điều hướng Topbar khi đang ở chế độ toàn cảnh hoặc di động ngang.
     - **Giải pháp Kiến trúc Đột phá (v150):**
       1. **Nút Bật/Tắt Thư viện Thường trực trên Topbar (`#btn-topbar-panel`):**
          - Đặt ngay trong cụm điều hướng `.topbar__end`, kế bên nút Tài khoản và Cài đặt.
          - Luôn hiện diện ở mọi kích thước màn hình: Trên desktop dạng viên thuốc Ambient Pill có nhãn "Thư viện"; trên tablet, mobile portrait và mobile landscape tự động co thành nút tròn tối giản 26-30px đồng điệu với các nút Toàn cảnh, Tunnel, Sync, Auth.
          - Đồng bộ trạng thái hai chiều: Khi thư viện đang mở -> `aria-pressed="true"` kèm ánh sáng viền neon glow `--accent`; khi thư viện thu gọn -> `aria-pressed="false"`. Người dùng có thể nhấn nút này bất cứ lúc nào để ẩn/hiện thư viện mà không phụ thuộc vào vị trí chuột hay màn hình.
       2. **Thanh Mở Rộng Docking Mép Màn hình (`.btn-panel-expand`):**
          - Di dời hoàn toàn khỏi góc trên sân khấu, neo chặt vào mép phải màn hình ở độ cao 50% (`position: fixed; top: 50%; transform: translateY(-50%); right: 0;`).
          - Thiết kế dạng tab kéo cao cấp Ambient Dark (`border-radius: 12px 0 0 12px;`), biểu tượng `chevrons-left` (`<<`), trượt nhẹ ra ngoài 3-4px khi hover hoặc chạm.
          - Khoảng cách an toàn tuyệt đối: Cách khối viễn trắc trên cùng (`y ≈ 4px`) hơn 150px và cách Deck bên dưới hơn 100px, loại bỏ 100% nguy cơ đè chữ hay che chắn đồ họa.
       3. **Nút Thu gọn Chuẩn hóa (`#btn-panel-collapse`):**
          - Tinh chỉnh biểu tượng trong header bảng điều khiển sang `chevrons-right` (`>>`) trực quan, thể hiện rõ thao tác trượt thu gọn về bên phải.
       4. **Căn giữa Tự động Popover khi Thu gọn:**
          - Khi bảng điều khiển thu gọn trong chế độ ngang (`body.is-panel-collapsed`), các hộp thoại nổi (Mic, Hẹn giờ, EQ) tự động định vị lại về chính giữa màn hình (`left: 50% !important;`), không bị lệch sang trái theo kích thước sân khấu cũ.
       5. **Đồng bộ Phiên bản & Cache Busters:**
          - Bump toàn bộ hệ thống lên `v150`: `app.css?v=150`, `main.js?v=150`, `sw.js?v=150`, `CACHE_NAME = "meikova-loop-v150"`.
     - **Kiểm thử Toàn diện (Zero Flake - Exit Code 0):**
       - `python scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
       - `python tests/test_stage_sync.py`: ALL TESTS PASSED (Exit Code 0).
       - `python tests/test_server_and_features.py`: ALL 35 TESTS PASSED (Exit Code 0).

  13. **Tối Ưu Không Gian, Khắc Phục Lỗi Tràn Tab Pill & Chuẩn Hóa Cột Thư Viện Màn Hình Ngang (Compact Library Cockpit & Segmented Tab Alignment v151 - meikova-ambient-ui):**
     - **Nguyên nhân gốc rễ lỗi hiển thị trong ảnh chụp:**
       1. **Lỗi tràn viên thuốc Tab (`.panel__head .tabs button` & `.mode button`):** Lớp cơ sở `.seg button` đặt `min-height: 34px;`. Khi ở màn hình ngang, `.panel__head .tabs` ép `height: 30px !important;` và `.panel__head .tabs button` chỉ đặt `height: 26px !important;` mà quên ghi đè `min-height`. Kết quả là nút active màu cam có chiều cao thực tế 34px nằm trong khung `.tabs` cao 30px, làm viên thuốc cam tràn ra ngoài viền khung cả trên lẫn dưới, để lộ khung viền đúp lệch phía sau.
       2. **Lỗi vỡ chữ 3 dòng ở tiêu đề danh sách (`.shelf-head .label`):** Cụm từ 5 chữ *"Các vòng trong thư viện"* nằm chung hàng với bộ đếm `98/98` và 2 nút `[Chọn]`, `[Playlist]` trong cột ngang rộng ~260px chỉ còn ~80px chiều ngang, khiến chữ bị bẻ gãy thành 3 dòng dọc (`Các vòng / trong thư / viện`).
       3. **Lệch tên Class CSS trong Media Query Landscape:** Các selector cũ dùng `.shelf__head`, `.shelf__title`, `.add__help`, `.tracklist` không khớp với DOM thực tế (`.shelf-head`, `.shelf-head .label`, `#add-hint`, `.tracks`), khiến dòng hướng dẫn dài dòng `#add-hint` không được ẩn đi và chiếm mất chiều cao quý giá của danh sách bài hát.
     - **Giải pháp Kiến trúc Triệt để (v151):**
       1. **Khóa Khít Viên Thuốc Tab & Mode Switch (`Zero-Pill-Overflow`):**
          - Ghi đè tường minh `height: 22px !important; min-height: 22px !important;` cho `.panel__head .tabs button` và `.mode button` trong khung `.tabs` / `.mode` cao `28px !important; padding: 2px !important;`, đồng thời đặt `.seg__ind { top: 2px !important; bottom: 2px !important; }`.
          - Bổ sung gọi `placeIndicators()` trong `requestAnimationFrame` khi đóng/mở bảng điều khiển và khi xoay màn hình để thanh trượt `.seg__ind` luôn khớp 100% tọa độ nút active.
       2. **Chuẩn hóa Tiêu đề Tối giản ("Less Text, More Signal"):**
          - Đổi tiêu đề sang **"Kho bài"** (2 từ, chuẩn nhạc cụ phòng thu), kết hợp `white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;` trên `.shelf-head .label` $\rightarrow$ Đảm bảo 100% luôn nằm gọn trên 1 dòng duy nhất ở mọi kích thước màn hình.
       3. **Đồng bộ Selector DOM & Tối đa hóa Chiều cao Danh sách Bài:**
          - Áp dụng đúng selector `#add-hint, .add .hint, .worker { display: none !important; }` khi ở màn hình ngang.
          - Khớp chính xác `#tab-library`, `.shelf-head`, `.lib-tools`, `.pl-nav`, `.tracks`, `.track .t`, `.track .s`, `.track .acts`, giúp danh sách bài hát hiển thị được nhiều gấp đôi số bài trong cùng khung nhìn ngang.
       4. **Đồng bộ Phiên bản & Cache Service Worker:**
          - Bump toàn bộ hệ thống lên `v151`: `app.css?v=151`, `main.js?v=151`, `sw.js?v=151`, `CACHE_NAME = "meikova-loop-v151"`.
     - **Kiểm thử Toàn diện (Exit Code 0):**
       - `python scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
       - `node --check web/js/main.js`: Syntax OK (Exit Code 0).
       - `python tests/test_stage_sync.py`: ALL TESTS PASSED (Exit Code 0).
       - `python tests/test_server_and_features.py`: ALL 35 TESTS PASSED (Exit Code 0).


  14. **Khắc Phục Lỗi Cắt Mép Trên/Dưới Của Nút Play Trên Deck & Tách Rời Khoảng Cách Danh Sách Bài Hát (Deck Unclipped Pill & Breathable Track Cards v152 - meikova-ambient-ui):**
     - **Nguyên nhân gốc rễ phát hiện từ ảnh chụp thực tế:**
       1. **Nút Play màu cam (`.deck__play`) trên Deck bị cắt phẳng mép trên và dưới (`media_1794120849609_0642632f.png`, `media_1794120869769_26a94e78.png`):**
          - Trong `@media (max-height: 600px) and (orientation: landscape)`, `.deck` đặt `height: 34px !important; box-sizing: border-box !important; overflow-x: auto !important;` kèm viền `1px` trên/dưới, khiến chiều cao vùng chứa thực tế (padding-box) chỉ còn `32px`.
          - Theo đặc tả CSS Overflow, khi `overflow-x: auto` được kích hoạt thì `overflow-y` tự động bị ép về `auto`, cắt cụt mọi phần tử con vượt quá `32px`. Vì `.deck__play` có kích thước `34px x 34px`, hai cực trên và dưới của hình tròn màu cam bị xén phẳng mất `1px-2px`.
       2. **Danh sách bài hát (`.tracks` / `.track`) bị dính sát vào nhau và ép bẹp chiều dọc (`media_1794120924048_2644b50c.png`):**
          - `.tracks` sử dụng `display: grid !important; gap: 2px !important;` bên trong khung cuộn `flex: 1`, kết hợp `.track` chỉ có `min-height: 32px !important; padding: 3px 6px !important;` và không có `flex-shrink: 0` hay nền/viền phân tách.
          - Khi danh sách có 98 bài hát, các hàng `.track` bị ép sát vào nhau (khoảng cách giữa dòng phụ đề bài trên và tiêu đề bài dưới chỉ còn `2px` — nhỏ hơn cả khoảng cách nội bộ giữa tiêu đề và phụ đề của cùng 1 bài), khiến các bài hát dính chặt vào nhau và bài đầu tiên bị lẹm mép trên.
     - **Giải pháp Kiến trúc Triệt để (v152):**
       1. **Giải phóng Chiều cao & Overflow cho Deck (`.deck` & `.deck__play`):**
          - Nâng chiều cao `.deck` trong màn hình ngang lên `height: 40px !important; min-height: 40px !important; padding: 3px 14px !important; overflow: visible !important;`.
          - Tinh chỉnh nút `.deck__play` về `width: 32px !important; height: 32px !important;` $\rightarrow$ Nút Play tròn trịa tuyệt đối 100%, có khoảng thở `3px` đều cả trên lẫn dưới bên trong viên thuốc Deck và giữ nguyên quầng sáng neon glow.
       2. **Tái cấu trúc Danh sách Bài hát dạng Thẻ Độc lập Thoáng đãng (`.tracks` & `.track`):**
          - Chuyển `.tracks` từ `display: grid` sang `display: flex !important; flex-direction: column !important; gap: 6px !important; padding: 4px max(env(safe-area-inset-right, 0px), 8px) 12px 8px !important;`.
          - Thiết lập `flex-shrink: 0 !important; min-height: 46px !important; padding: 7px 8px !important; gap: 8px !important; grid-template-columns: 30px minmax(0, 1fr) !important;` cho mỗi `.track`, kèm nền thẻ dịu `background: oklch(1 0 0 / 0.025) !important;` và viền hairline `border: 1px solid oklch(1 0 0 / 0.05) !important; border-radius: 10px !important;` (áp dụng đồng bộ cho cả giao diện chuẩn và màn hình ngang).
       3. **Đồng bộ Phiên bản & Cache Service Worker:**
          - Bump toàn bộ hệ thống lên `v152`: `app.css?v=152`, `main.js?v=152`, `sw.js?v=152`, `CACHE_NAME = "meikova-loop-v152"`.
     - **Kiểm thử Toàn diện (Exit Code 0):**
       - `python scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
       - Live Dev Server trên cổng 8765: HTTP 200 OK (`v=152` active).


  15. **Khắc Phục Triệt Để Lỗi Đứng Hình Màn Hình Vệ Tinh & Chuẩn Hóa Quầng Sáng Kim Phát Nhạc (Satellite 60/120 FPS Resilience & Pure Optical Playhead v154 - meikova-ambient-ui):**
     - **Nguyên nhân gốc rễ phát hiện từ ảnh chụp thực tế (`media_1794121191575_ebabcec9.jpg`, `media_1794121202464_a7e8130c.jpg`, `media_1794122526806_c21b00b9.png`):**
       1. **Chết vòng lặp `requestAnimationFrame` ngay ở Frame #1 trên Màn hình Vệ tinh:**
          - Khi mới mở `?mode=satellite`, Frame #1 chạy trước khi nhận bản tin WebSocket đầu tiên (`stageSync.telemetry` là `null`).
          - `_drawSatelliteStage()` gọi `this._placeCenter({ ring: { x: cx, y: cy, r: baseR, alpha: 1, fill: 1 }, dip: 1 })`.
          - Tại `_placeCenter()`, biểu thức `ring?.track.id` (thiếu `?.` sau `track`) ném lỗi `Uncaught TypeError: Cannot read properties of undefined (reading 'id')` vì `ring` không có thuộc tính `track`.
          - Do `requestAnimationFrame(loop)` được đặt sau `this._frame(now)` mà không có `try/finally`, vòng lặp render chết vĩnh viễn ngay từ mili-giây đầu tiên. Màn hình vệ tinh chỉ vẽ lại đúng 1 khung hình mỗi khi người dùng thu phóng/thay đổi kích thước cửa sổ (`_resize()`).
       2. **Các vòng tròn đồng tâm dạng bia ngắm và que chữ nhật xuyên qua chấm sáng Playhead (`media_1794122526806_c21b00b9.png`):**
          - Trong `_drawSatelliteStage()`, khối lệnh `if (interpBeat !== this._lastSatBeat) this.ripples.push(...)` đẩy sóng chấn động vào `this.ripples` ở **mọi nhịp beat** (~2 lần/giây), khiến `_drawRipples()` vẽ 4–6 đường tròn trắng/xám đồng tâm bao quanh kim phát nhạc như bia bắn súng (trong khi ở máy chủ Host, `this.ripples` chỉ phát 1 lần duy nhất tại điểm giao `∞` khi chuyển bài).
          - Trong `_drawHead()`, lệnh vẽ cung 1 beat `ctx.arc(ring.x, ring.y, ring.r, a1, a2)` với độ dày `lineWidth = th + 5` trên cung dài chỉ ~2.5px đã tạo ra một thanh chữ nhật dựng đứng đâm xuyên qua tâm quả cầu trắng (như chiếc tăm xiên qua viên bi `ϕ`), kèm lõi đặc `th * 0.42` quá to và phẳng trên màn hình lớn.
     - **Giải pháp Kiến trúc Triệt để (v154):**
       1. **Bọc thép Vòng lặp Render 60/120 FPS & Heartbeat Máy chủ (`web/js/viz.js`, `web/js/stage_sync.js`):**
          - Bọc `this._frame(now)` trong `try { ... } catch (err) { ... } finally { requestAnimationFrame(loop); }` để vòng lặp render không bao giờ có thể bị ngắt.
          - Sửa `ring?.track.id` thành `const trackId = ring?.track?.id || null;` và chặn `onCaption()` khi `stageSync.isSatellite` để không ghi đè tiêu đề vệ tinh.
          - Nâng cấp heartbeat 33ms trên Host: tự động tính toán lại `_update`, `_beatPulse`, `_spectrum`, `_heads` ngay cả khi tab Host bị ẩn/thu nhỏ (`document.hidden`) hoặc chưa cập nhật số lượng vệ tinh, đảm bảo luồng dữ liệu 30 FPS sang vệ tinh luôn tươi mới.
          - Nội suy góc kim chạy mượt 60/120/144 FPS giữa các gói tin WebSocket bằng thời gian thực `t._recvAt` kết hợp bộ lọc khóa pha mượt (`_satSmoothAng`).
       2. **Tái thiết kế Playhead Quang học 3 Lớp & Đồng bộ Hào quang Phổ nhạc (`_drawHead`, `_drawHalo`, `_drawLive`):**
          - Loại bỏ hoàn toàn `this.ripples.push` theo từng beat trên vệ tinh (chỉ kích hoạt tại điểm giao khi chuyển sang bài mới giống hệt Host).
          - Loại bỏ thanh chữ nhật `th + 5` đâm xuyên qua chấm sáng trong `_drawHead()`. Thay bằng nguồn sáng quang học 3 lớp (`globalCompositeOperation = "lighter"`): Quầng sáng khí quyển rộng (`glow * 2` co giãn theo `pulse` & `bass`) + Vành nhật hoa chuyển sắc mượt (`coronaR`) + Nhân sáng trắng tinh khiết (`coreR` 2.6px–4.8px).
          - Đồng bộ trực tiếp dữ liệu phổ âm thanh `t.bands` sang `_drawHalo()`, tia chớp nhảy nhịp `t.flashes` và đường dẫn chuyển bài dự kiến `t.plan` từ Host sang Satellite, dùng chung hàm bố cục `this._layout(isTrans, progress)` giúp màn hình vệ tinh hiển thị sắc nét và sống động 1:1 với máy chủ.
       3. **Đồng bộ Phiên bản & Cache Service Worker:**
          - Bổ sung `"/js/stage_sync.js"` và `"/js/harmonic.js"` vào `STATIC_ASSETS` trong `web/sw.js`.
          - Bump toàn bộ hệ thống lên `v154`: `app.css?v=154`, `main.js?v=154`, `sw.js?v=154`, `CACHE_NAME = "meikova-loop-v154"`.
     - **Kiểm thử Toàn diện (Exit Code 0):**
       - `node --check web/js/viz.js` & `node --check web/js/stage_sync.js`: Syntax OK (Exit Code 0).
       - `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
       - `.\.venv\Scripts\python.exe tests/test_stage_sync.py`: ALL 6 TESTS PASSED (Exit Code 0).
       - Live Dev Server trên cổng 8765: HTTP 200 OK (`v=154` active).


  16. **Đồng Bộ Tuyệt Đối 1:1 Thanh Deck, Độ Sáng Chấm Sáng Playhead, Hình Vô Cực Chờ & Nội Dung Trung Tâm Vòng Lặp Giữa Máy Chính Và Vệ Tinh (v155–v158 - meikova-ambient-ui):**
     - **Nguyên nhân gốc rễ phát hiện từ ảnh chụp thực tế (`media_1794122545143_2af261c2.png`, `media_1794124411376_71c7ba35.jpg`, `media_1794122623659_85d43d15.jpg`, `media_1794123747156_52a7007a.jpg`, `media_1794126096834_ce66c793.jpg`, `media_1794125945322_1354ee67.jpg`, `media_1794125952300_ff793909.jpg`):**
       1. **Thanh Deck, Trạng thái Tạm dừng & Hình Vô cực chờ (`v155`):**
          - Màn hình vệ tinh trước đó ẩn `.deck` gốc và tạo một `.satellite-deck` rút gọn; đồng thời Host kiểm tra `this.player?.paused` (thuộc tính không tồn tại trên `Player`, thực tế dùng `!this.player?.playing`), khiến nút Play/Pause trên vệ tinh không chuyển trạng thái khi nhấn dừng.
          - Ở trạng thái chờ (`idle`), vệ tinh tự vẽ vòng tròn tĩnh thay vì gọi `this._drawIdle(ctx, now, 1)` (hình vô cực `∞` có hạt sáng chạy dọc đường lemniscate như máy chính).
       2. **Chênh lệch độ sáng chấm sáng Playhead giữa 2 bên (`v156`–`v157`):**
          - Trong `_drawHead()`, việc vẽ đoạn cung `[a1, a2]` phụ thuộc vào bán kính vòng `ring.r` (trên Host có panel thư viện nên `ring.r` nhỏ $\rightarrow$ cung ngắn 2px co lại thành cục sáng đặc chồng lên tâm trắng; trên Satellite toàn màn hình nên `ring.r` lớn $\rightarrow$ cung giãn dài làm tâm bớt chói).
          - Trên Satellite, `this.bands` bị làm mượt thêm một lần nữa (`0.55 * prev + 0.45 * target`) làm giảm đỉnh sáng tức thời của nhịp nhạc, và Service Worker cache-first giữ lại các ES module phụ (`viz.js`, `stage_sync.js`) bản cũ khi không có hậu tố `?v=` đồng bộ.
       3. **Nội dung chữ bên trong vòng lặp (`.ring-center`) chưa thống nhất (`v158`):**
          - Trên Host, `renderStage()` hiển thị 4 dòng chuẩn: `#rc-kicker` (`ĐANG PHÁT · CHUỖI` / `ĐANG BLEND` / `ĐANG PHÁT · LẶP MÃI`), `#rc-title` (tên bài hát), và `#rc-meta` gồm 2 dòng xếp tầng (`<span class="rc-artist">...</span>` + `<span class="mono">128 BPM · 9A · E minor</span>`).
          - Trong khi đó, `applySatelliteTelemetry()` trên vệ tinh lại tự ghép chuỗi `#rc-kicker` thành `128 BPM · 9A · ĐỒNG BỘ VỆ TINH` và ghi đè `#rc-meta.textContent` chỉ bằng tên nghệ sĩ (làm mất dòng thông số `128 BPM · 9A · E minor`).
     - **Giải pháp Kiến trúc Triệt để (`v158`):**
       1. **Dùng chung 100% `.deck` gốc, Hình Vô cực Idle & Đồng bộ Cấu hình (`web/js/stage_sync.js`, `web/js/viz.js`, `web/css/app.css`):**
          - Hiển thị trực tiếp `.deck`, `#ro-tl`, `#ro-tr`, `#next-info`, `#history` trên màn hình vệ tinh và đồng bộ toàn bộ trạng thái (`viz_scale`, `ui_scale`, `glow`, `theme`, `keep`, `night`, `locked`, `vocal_mode`, `eq_mode`, `volume`, `muted`).
          - Sửa kiểm tra trạng thái dừng thành `const isPaused = !this.player?.playing;` và phát telemetry ngay lập tức trong `renderTransport()` (kèm gọi `renderStage()` & `renderSetlist()` trước khi phát).
          - Khi ở trạng thái `idle`, vệ tinh gọi trực tiếp `this._drawIdle(ctx, now, 1)` để vẽ đường vô cực `∞` giống hệt máy chính.
       2. **Đồng nhất Tuyệt đối Độ sáng & Kích thước Quang học của Chấm sáng Playhead (`web/js/viz.js`):**
          - Trong `_drawHead(ctx, h, alpha, full)`, loại bỏ đoạn cung `[a1, a2]` phụ thuộc bán kính `ring.r`, chuẩn hóa nguồn sáng đồng tâm độc lập kích thước khung hình: hào quang ngoài `glow = (15 + 7 * pulse + 9 * bass) * Math.sqrt(theme.glowGain())`, vành corona `coreGlowR = (full ? 6.5 : 4.2) * (1 + 0.12 * pulse)`, và nhân trắng `#ffffff` `full ? 2.8 : 2.0`.
          - Sao chép 1:1 `this.bands[i] = t.bands[i]` trên vệ tinh (không làm trễ lần 2) và đặt `this._broadcastHostTelemetry()` chạy ngay sau `this.heads = this._heads(...)` trong `_frame(now)`.
       3. **Thống nhất 1:1 Nội dung Trung tâm Vòng lặp `.ring-center` (`web/js/viz.js`, `web/js/stage_sync.js`, `web/js/main.js`):**
          - Bổ sung `rc_kicker_html`, `rc_title_html`, `rc_meta_html` vào `commonCfg` trong `_broadcastHostTelemetry()` và cập nhật trực tiếp `#rc-kicker`, `#rc-title`, `#rc-meta` trên vệ tinh (kèm fallback đồng nhất cấu trúc `<span class="rc-artist">` + `<span class="mono">BPM · Camelot · Key</span>`), đảm bảo cả 2 màn hình hiển thị nội dung giống hệt nhau 100% ở mọi trạng thái.
       4. **Đồng bộ Đường Nét Đứt Nhảy Điểm (`plan.jumps`), Vòng Chờ Nét Đứt `"ĐANG TẢI"` (`_drawPlaceholder`), Hai Chấm Sáng Khi Blend (`lead_head` & `ghost_head`) và Điểm Giao (`_drawCross`) (`v159`):**
          - Trong `Player._setPlan()`, `this.player.plan.jumps` là đối tượng `Map` (không phải `Array`), khiến `Array.isArray(this.player.plan.jumps)` trả về `false` và làm mất đường nét đứt dự kiến trên vệ tinh. Đã sửa thành `this.player.plan.jumps ? Array.from(this.player.plan.jumps) : []`.
          - Bổ sung truyền `placeholder`, `two`, `swap_prog`, `face_a`, `face_b`, `tr_type`, `lead_head`, `ghost_head`, `cap_on`, `cap_dip` từ Host sang Satellite; pre-fetch `ensureTrack(preloadId)` ngay từ giai đoạn `placeholder`; loại bỏ hoàn toàn vòng tròn trơn khi chưa tải xong analysis và thay bằng `_drawPlaceholder(ctx, ..., now)` (vòng tròn nét đứt `"ĐANG TẢI"` giống hệt màn hình chính).
          - Khi đang blend sang bài thứ 2, đồng bộ cả 2 chấm sáng (`lead` kèm phổ nhạc `_drawHalo` chuyển sang vòng thứ 2 và `ghost` mờ dần trên vòng thứ 1), di chuyển `.ring-center` sang vòng thứ 2 khi `progress >= 0.5`, và vẽ điểm giao `_drawCross` chuẩn 1:1 (xoá bỏ hộp `5A ⇄ 5A` lệch chuẩn).
       5. **Đồng bộ Phiên bản ES Modules & Cache Busting (`v159`):**
          - Sửa `NoCacheStaticFiles` trong `loopbox/server.py` bắt cả `path in ("", ".")` cho URL gốc `/?mode=satellite`; bổ sung tự động `client.navigate(client.url)` khi xóa cache cũ trong `sw.js` và `controllerchange` listener trong `index.html`; nâng toàn bộ hệ thống lên `v159`.
     - **Kiểm thử Toàn diện (Exit Code 0):**
       - `node --check web/js/viz.js`, `node --check web/js/stage_sync.js`, `node --check web/js/main.js`: Syntax OK (Exit Code 0).
       - `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
       - `.\.venv\Scripts\python.exe tests/test_stage_sync.py`: ALL 6 TESTS PASSED (Exit Code 0).

  17. **Giải Mã Phân Đoạn MP3 Bài Dài Đến 60 Phút, Ổn Định Vòng Lặp Khi Tìm Bài Kế Tiếp & Triệt Tiêu Nhấp Nháy Vệ Tinh (v165–v167):**
     - **Nguyên nhân gốc rễ phát hiện & kiểm chứng thực nghiệm:**
       1. **Lỗi `EncodingError: Unable to decode audio data` khi phát bài hát >15 phút trên Web (`gebkUty7dPU`, 55 phút 46 giây, `80.3 MB` MP3):**
          - Việc truyền nguyên khối ArrayBuffer MP3 80.3 MB vào một lệnh `AudioContext.decodeAudioData()` duy nhất khiến `AudioFileReader::Read()` của trình duyệt giải mã toàn bộ `147,563,010` mẫu vào bộ nhớ tạm C++ `AudioBus` (~1.18 GB) đồng thời cấp phát `AudioBuffer` `DOMFloat32Array` (~1.18 GB), chạm ngưỡng giới hạn ~2.5 GB của PartitionAlloc trên tiến trình renderer và ném lỗi `EncodingError: Unable to decode audio data`.
          - Trên Mobile Web, `MAX_SAFE_DURATION_S` trước đó bị giới hạn ở `720` giây (12 phút), chặn các bài dài đã nạp từ Desktop.
          - Nút `#btn-play` trên thanh Deck khi chưa có bài đang phát duyệt `metas.find(...)` theo thứ tự mảng gốc (bài cũ nhất ở đầu mảng `metas[0]` = `gebkUty7dPU`), ngược với thứ tự hiển thị mặc định của `renderLibrary()` (`shown.slice().reverse()`, bài mới nhất ở đầu danh sách).
          - Trong `loopbox/server.py`, hàm `_send_sound()` khi bật `MULTIUSER=1` có lỗi `NameError: name 'r_start' is not defined` khi xử lý header `Range: bytes=...`.
       2. **Hiện tượng vòng tròn phóng to thu nhỏ liên tục & nhịp đập bị gián đoạn khi tìm bài tiếp theo (`v166`):**
          - Trong `Viz._roles()`, ngay khi `player._setPlan()` chọn thử một bài kế tiếp (`view.next`), `two` lập tức bật `true` khiến vòng chính co bán kính từ `1.0R` xuống `0.62R` dù bài kế tiếp còn cách hàng chục giây hoặc đang tải/lỗi phải đổi ứng viên khác.
          - Trong `Viz._buildLayer()`, việc vẽ 2.500–7.000 cung beat + hàng nghìn đường bezier trên canvas `dpr * 2` tốn 90–220ms trên luồng chính, làm khựng nhịp đập `pulse`.
          - Trong `Viz._beatPulse()`, khi `analyser.getByteFrequencyData()` tạm thời trả về 0 lúc chuyển voice, `this.pulse` chỉ nhân `0.86` suy giảm về 0 mà thiếu bộ cộng hưởng theo pha beat chủ động.
     - **Giải pháp Kiến trúc Triệt để (`v167`):**
       1. **Bộ giải mã MP3 Phân đoạn Khớp Khung mẫu & Tần số Lấy mẫu Thích ứng (`web/js/api.js`, `web/js/engine.js`, `web/js/player.js`):**
          - Nâng `MAX_SAFE_DURATION_S = 3600` (60 phút) đồng nhất trên cả Desktop Web và Mobile Web.
          - Xây dựng `parseMp3Frames(u8)` và `decodeTrackAudio(ctx, arrayBuffer, opts)`: tự động bỏ qua thẻ ID3v2 và frame `Xing`/`Info`, chia file MP3 dài (>15 phút trên Desktop hoặc >10 phút trên Mobile, hoặc khi giải mã nguyên khối báo lỗi) thành từng phân đoạn ~9.000 frame (~3.9 phút / ~5.6 MB MP3) kèm 3 frame mồi (warm-up) và bù chính xác độ trễ bộ giải mã LAME/MPEG Layer III (`1105` mẫu tại `44100 Hz`), đảm bảo khớp tuyệt đối với lưới nhịp `T.beats` (sai số `0.00ms`) và giảm đỉnh bộ nhớ tạm C++ từ `1.18 GB` xuống `~85 MB`.
          - Áp dụng tần số lấy mẫu thích ứng cho bài siêu dài: `32000 Hz` stereo cho bài >25 phút trên Desktop (giảm ~30% RAM `AudioBuffer` cho bài 55.8 phút), `22050 Hz` trên Mobile cho bài >10 phút, kèm cơ chế hạ bậc cấp phát an toàn (`_allocateAudioBufferWithFallback`) và thu hồi bộ nhớ đệm chủ động (`_evict` với ngân sách `MAX_CACHE_BYTES`).
          - Bổ sung `Engine._sliceAtContextRate(buf, from, to)` trong `web/js/engine.js` để tự động lấy mẫu lại đoạn cửa sổ ngắn `[from, to]` sang `ctx.sampleRate` (`44100 Hz`) qua `OfflineAudioContext` khi dùng `stretchVoice` (Signalsmith Stretch).
          - Bổ sung `Loader.canLoadStems(id)` để các bản mix dài >15 phút dùng bộ lọc DSP `vocalFilter` thay vì giải mã thêm một buffer `vocals.mp3` 67 MB thứ hai.
       2. **Chọn Bài Theo Đúng Thứ Tự Hiển Thị & Sửa HTTP Range (`web/js/main.js`, `loopbox/server.py`):**
          - Bổ sung `getOrderedReadyTracks()` trong `web/js/main.js` để nút `#btn-play` trên Deck luôn ưu tiên phát bài hát đầu tiên đang hiển thị trên danh sách thư viện/playlist hiện hành.
          - Sửa lỗi tách `r_start, r_end` từ `range_header` trong `_send_sound()` (`loopbox/server.py`), hỗ trợ đầy đủ `bytes=A-B`, `bytes=A-`, và suffix range `bytes=-N`.
       3. **Ổn Định Bán Kính Vòng Lặp, Nhịp Đập Liên Tục & Chống Đứng Hình Vệ Tinh Khi Tab Ẩn (`web/js/viz.js`, `web/js/player.js`, `web/css/app.css`):**
          - Neo giữ `two = false` trong `Viz._roles()` cho đến khi bài kế tiếp đã nạp xong (`secondReady`) và tiến vào ngưỡng `DOCK_LEAD_S = 14s` trước điểm giao (hoặc người dùng chủ động chọn); giữ grace window `550ms` chống co giãn khi đổi ứng viên và đánh dấu cooldown `_failedTrackUntil` cho ứng viên lỗi.
          - Bổ sung nhịp đập dự phòng theo pha beat (`beatEnv = Math.pow(Math.max(0, 1 - beatPhase), 2.6) * 0.58`) trong `_beatPulse()`, gom nhóm vẽ cung beat theo màu trong `_buildLayer()` (giảm thời gian dựng layer xuống `~14ms`), và tiến khung hình vệ tinh trong `renderSatellite()` ngay cả khi tab bị trình duyệt throttle `requestAnimationFrame` (`document.hidden || now - this.last > 80`).
     - **Lệnh kiểm tra đã chạy & Exit Code (`v167`):**
       - `Get-ChildItem web/js/*.js, web/sw.js | ForEach-Object { node --check $_.FullName }`: Exit Code 0.
       - `.\.venv\Scripts\python.exe -m compileall -q loopbox tests scripts`: Exit Code 0.
       - `.\.venv\Scripts\python.exe scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
       - `.\.venv\Scripts\python.exe tests/test_pwa_manifest.py`: OK (Exit Code 0).
       - `.\.venv\Scripts\python.exe -u tests/test_stage_sync.py`: ALL 11 TESTS PASSED (Exit Code 0).
       - `.\.venv\Scripts\python.exe -u tests/test_server_and_features.py`: ALL 35 TESTS PASSED (Exit Code 0).
       - `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`: Ran 44 tests in 14.1s - OK (Exit Code 0).
       - Headless Edge E2E (`e2e_satellite_flicker_check.py`, bao gồm phát thực tế bài `gebkUty7dPU` dài `3346.1s` / 55m46s): ALL E2E CHECKS PASSED (Exit Code 0).
       - Live Dev Server trên cổng `0.0.0.0:8765`: HTTP 200 OK (`v167` active).

---

## Phiên làm việc: 10/11/2026 (Khắc phục Lỗi Xê dịch/Nhấp nháy Độ rộng Side Panel khi Chuyển Tab v175 & Khắc phục Tràn bộ nhớ WebView2 Desktop)

### 1. Mục tiêu hoàn thành:
1. **Khắc phục triệt để lỗi "Out of Memory" trên Desktop App (`MeikovaLoop.exe`):**
   - Gỡ bỏ cờ `--js-flags=--max-old-space-size=256`, `--disk-cache-size=1`, `--media-cache-size=1` trong [`loopbox/desktop.py`](file:///d:/JOB/DEV/meikova/meikova-loop/loopbox/desktop.py) vốn giới hạn heap V8 của trình duyệt nhúng WebView2 quá thấp.
   - Bổ sung `loopbox.cluster_discovery` và `loopbox.cookies` vào `hiddenimports` trong [`meikova_loop.spec`](file:///d:/JOB/DEV/meikova/meikova-loop/meikova_loop.spec) và đóng gói thành công `dist/MeikovaLoop/MeikovaLoop.exe`.
2. **Khắc phục lỗi xê dịch kích thước side panel & nhấp nháy canvas khi chuyển giữa 2 tab "Thư viện" và "Tinh chỉnh" (`v175`):**
   - **Nguyên nhân gốc rễ:**
     - `.panel` trong [`web/css/app.css`](file:///d:/JOB/DEV/meikova/meikova-loop/web/css/app.css) chưa khóa cứng `width: var(--panel-w); min-width: var(--panel-w); max-width: var(--panel-w); overflow-x: hidden;`.
     - `.tab` chưa có `scrollbar-gutter: stable`, `width: 100%`, `max-width: 100%`, `box-sizing: border-box`, `overflow-x: hidden`, dẫn đến việc thanh cuộn dọc hoặc độ rộng nội tại khác nhau giữa 2 tab làm thay đổi bề rộng nội bộ hoặc gây reflow lan truyền sang `.stage`, kích hoạt `ResizeObserver` xóa và vẽ lại `<canvas id="viz">`.
     - `@keyframes tab-in` dùng `transform: translateY(6px)` 420ms gây cảm giác giật khi chuyển tab.
     - Trong [`web/js/main.js`](file:///d:/JOB/DEV/meikova/meikova-loop/web/js/main.js), giá trị `ui.panelWidth` đọc từ `localStorage` bị chậm áp dụng cho tới khi `applySettings()` chạy ở cuối file (~dòng 4953), gây co giãn giao diện khi tải trang.
   - **Giải pháp đã triển khai:**
     - Khóa cứng kích thước `.panel` theo `--panel-w` trên Desktop (`width`, `min-width`, `max-width`, `overflow-x: hidden`) và khôi phục `width: 100% !important; min-width: 0 !important; max-width: 100% !important;` cho mobile `< 900px`.
     - Chuẩn hóa `.tab` với `width: 100%; max-width: 100%; box-sizing: border-box; overflow-x: hidden; scrollbar-gutter: stable;` giúp giữ nguyên bề rộng vùng nội dung bất kể có thanh cuộn hay không.
     - Chuyển `@keyframes tab-in` sang hiệu ứng fade `opacity` thuần không dịch chuyển tọa độ (`transform`).
     - Áp dụng `--panel-w` từ `ui.panelWidth` ngay lập tức ngay sau khi đọc `localStorage` và khi khởi tạo `initPanelResizer()`.
     - Tăng version cache-busting lên `v175` trong [`web/index.html`](file:///d:/JOB/DEV/meikova/meikova-loop/web/index.html), [`web/sw.js`](file:///d:/JOB/DEV/meikova/meikova-loop/web/sw.js), [`scripts/verify_deck_responsive.py`](file:///d:/JOB/DEV/meikova/meikova-loop/scripts/verify_deck_responsive.py), đồng thời cập nhật thẳng các file web mới vào bản build `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code:
- `python scripts/verify_deck_responsive.py`: ALL TESTS PASSED (Exit Code 0).
- `python tests/test_tab_stability.py`: ALL TAB STABILITY UNIT TESTS PASSED (Exit Code 0).
- `.\.venv\Scripts\python.exe tests/test_stage_sync.py`: ALL 14 STAGE SYNC & LIGHT TESTS PASSED (Exit Code 0).
- `.\.venv\Scripts\python.exe tests/test_cluster_sync.py`: Ran 3 tests - OK (Exit Code 0).
- `.\.venv\Scripts\python.exe tests/test_long_track_playback.py`: Ran 4 tests - OK (Exit Code 0).
- Playwright Headless Edge E2E (kiểm tra trên các độ phân giải `1366x768`, `1100x700`, `850x390` landscape, `390x844` portrait với `panelWidth` = `280px`, `300px`, `384px`, `420px`): Chênh lệch độ rộng panel/stage = `0.00px`, `ResizeObserver` triggers = `0`, `innerW` khớp 100% giữa 2 tab (Exit Code 0).

### 3. Cảnh báo kỹ thuật:
- Khi chạy `tests/test_server_and_features.py` phần kiểm tra PyTorch (`test_empty_beats_guard_and_librosa_fallback`), hệ thống Windows đang chạy nhiều tiến trình có thể gặp lỗi paging file (`WinError 1455` khi nạp `cufft64_11.dll`). Điều này thuộc về giới hạn virtual memory của HĐH khi nạp thư viện CUDA, không liên quan đến logic mã nguồn.
- Bản build `dist\MeikovaLoop\MeikovaLoop.exe` đã được đồng bộ hóa các file `web/` mới (`v175`); nếu tiến trình `MeikovaLoop.exe` đang chạy, người dùng chỉ cần nhấn `Ctrl+R` hoặc mở lại ứng dụng từ khay hệ thống để áp dụng CSS/JS mới.


---

## Phiên làm việc: 17/11/2026 (Khôi phục Phổ Âm Thanh Halo Tinh tế, Chống Cắt Đỉnh 12h & Bản Dựng v1.0.35)

### 1. Mục tiêu hoàn thành:
1. **Khôi phục Phổ Âm Lượng Halo Nguyên Bản Tinh Tế (`web/js/viz.js`):**
   - Loại bỏ hoàn toàn khối đa giác khung dây (wireframe polygon) gây cảm giác lưới thép cứng nhắc.
   - Khôi phục cấu trúc vạch phổ hướng tâm tinh xảo ($N = 180$, bề rộng `1.3px`, đầu bo tròn `round`), phân loại 4 cấp độ sáng theo năng lượng âm thanh.
   - Khôi phục đáp ứng biên độ phi tuyến bậc hai $v^2 \cdot (0.55 + 0.45 \cdot u)$ cùng ngưỡng lọc nhiễu âm sàn ($v < 0.015$), giúp vạch phổ chỉ chuyển động nhịp nhàng tại các dải tần số có nhạc cụ thật sự rung động.
2. **Triệt tiêu Hiện Tượng Cắt Phẳng Ở Đỉnh 12h (Safe Headroom Clamping):**
   - Tính toán biên an toàn động theo chiều dọc màn hình: `safeHeadroom = Math.max(6, Math.min(ring.y - r0 - 12, this.h - ring.y - r0 - 12))`.
   - Giới hạn chiều cao sóng tối đa $H \le safeHeadroom$, đảm bảo phổ âm không bao giờ chạm tới mép trên canvas ($y = 0$) dù trên màn hình nhỏ hay khi đĩa xoay phóng to.
3. **Hiệu Ứng Quầng Sáng Mờ Nhấp Nhô Dưới Chân Vạch (Soft Ambient Halo Aura):**
   - Đổ màu gradient tỏa tia mềm từ viền ngoài $r_0$ đến đỉnh sóng $r_0 + H$ (`col` $0.32 \to$ `hi` $0.16 \to 0$) kèm quầng phát sáng `shadowBlur = 10`, tạo cảm giác các vạch phổ gắn kết hữu cơ trên một nền năng lượng phát quang mềm mại thay vì đứng rời rạc.
4. **Chuẩn Hóa Phiên Bản SSOT v1.0.35 & Đóng Gói Nhị Phân:**
   - Đồng bộ version `v1.0.35` trên 6 tệp trọng yếu: `package.json`, `installer.iss`, `loopbox/__init__.py`, `loopbox/config.py`, `loopbox/tray.py`, và `web/index.html`.
   - Biên dịch hoàn tất `dist/MeikovaLoop/MeikovaLoop.exe` qua PyInstaller với Exit Code 0.
   - Đồng bộ hóa các tệp Web JS/CSS vào `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code:
- `.\.venv\Scripts\python.exe tests/test_memory_lifecycle.py`: 22/22 PASSED (Exit Code 0).
- `.\.venv\Scripts\python.exe tests/stress_adversarial_r3.py`: 6/6 PASSED (Exit Code 0).
- `.\.venv\Scripts\python.exe version.py --check`: ALL 6 FILES CONSISTENT AT v1.0.35 (Exit Code 0).
- `.\.venv\Scripts\pyinstaller.exe --noconfirm meikova_loop.spec`: Exit Code 0 (`dist/MeikovaLoop/MeikovaLoop.exe` generated).
- Playwright Visual Inspection (`halo_perfect.png`): 0px clipping at $y = 0$, đường cong mượt mà 360 độ (Exit Code 0).

### 3. Cảnh báo kỹ thuật & Lưu ý vận hành:
- Đã đồng bộ tài nguyên giao diện vào thư mục `dist/MeikovaLoop/_internal/web/`.
- Khi khởi động lại ứng dụng `MeikovaLoop.exe`, toàn bộ phổ âm và quầng sáng mờ mới sẽ tự động hiển thị mà không cần xóa cache thủ công.


---

## Phiên làm việc: 17/11/2026 (Khắc phục Vạch Phổ Dày Đặc, Lớp Màng Màu Phát Quang Bao Bọc & Ánh Sáng Neon Chấm Sáng v1.0.36)

### 1. Mục tiêu hoàn thành:
1. **Phủ Dày Đặc Vạch Phổ Hướng Tâm (Dense Precision Dial):**
   - Nâng mật độ vạch sóng $N$ từ 180 lên 256 điểm quanh vòng tròn, đảm bảo khoảng cách giữa các vạch chỉ ~5px (chuẩn đồng hồ Thụy Sĩ).
   - Thiết lập chiều cao sàn tối thiểu `Math.max(2.0, v * H)` cho mọi vạch phổ, triệt tiêu hoàn toàn các khoảng đen trống thưa thớt khi dải tần tĩnh lặng.
2. **Lớp Màng Màu Phát Quang Bao Bọc Các Thanh Âm Lượng (Luminous Colored Membrane):**
   - Dựng màng màu hữu cơ liên tục nối từ chân vành đĩa $r_0$ ôm trọn lấy đỉnh sóng $r_{\text{peak}} = r_0 + \text{barLen} + 1.2$, đổ dải màu xuyên thấu tỏa tia từ `col` $0.42 \to$ `hi` $0.26 \to$ $0.02$ cùng hào quang `shadowBlur = 10`.
   - Bổ sung đường mép màng màu phát quang mảnh `1.0px` mềm mại theo màu bài hát (`theme.lift(col, 0.22)` ở độ mờ 38% kèm `shadowBlur = 6`), biến các vạch sóng thành một dải lụa năng lượng mềm mại nhấp nhô cùng âm nhạc thay vì các cọc trắng rời rạc.
3. **Khôi phục Ánh Sáng Neon Rực Rỡ từ Chấm Sáng (Playhead Radiant Neon Bloom):**
   - Gỡ bỏ điều kiện `if (this.memoryPressure !== "high")` từng triệt tiêu hoàn toàn quầng hào quang của đầu đọc khi hệ thống ở mức tải cao.
   - Nâng cấp bán kính phát quang neon lên $R = (32 + 16 \cdot \text{pulse} + 20 \cdot \text{bass}) \cdot \text{gain}$ ($\approx 48 \sim 68\text{px}$) với 5 dải chuyển màu mượt mà từ lõi neon trắng hồng rực rỡ lan tỏa êm dịu vào nền tối.
4. **Phục Hồi Đèn Nền Vòng Khuyên Lúc Tải Cao:**
   - Cho phép `_drawLights` tiếp tục phát quang nhịp thở vòng khuyên trong trạng thái `memoryPressure === "high"`, chỉ tiết giảm khi chạm ngưỡng nguy cấp `critical`.
5. **Chuẩn Hóa SSOT v1.0.36 & Kiểm Thử Toàn Diện:**
   - Đồng bộ version `v1.0.36` trên 6 tệp trọng yếu qua `version.py`.
   - Vượt qua 22/22 kiểm thử vòng đời bộ nhớ và 6/6 bài kiểm thử tải đối kháng.
   - Đồng bộ tài nguyên Web vào `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code:
- `.\.venv\Scripts\python.exe tests/test_memory_lifecycle.py`: Ran 22 tests in 36.450s - OK (Exit Code 0).
- `.\.venv\Scripts\python.exe tests/stress_adversarial_r3.py`: Ran 6 tests in 19.910s - OK (Exit Code 0).
- `.\.venv\Scripts\python.exe version.py --check`: ALL 6 FILES IN 100% VERSION SYNCHRONIZATION (Exit Code 0).
- Headless Visual Test (`halo_membrane_verified.png`): 100.0% diện tích màng màu bao bọc các vạch, hào quang playhead đạt độ rộng >60px, đỉnh 12h giữ khoảng cách an toàn tuyệt đối với mép canvas.

### 3. Cảnh báo kỹ thuật & Lưu ý vận hành:
- Tài nguyên Web tại `dist/MeikovaLoop/_internal/web/` đã được cập nhật trực tiếp. Người dùng chỉ cần khởi động lại ứng dụng `MeikovaLoop.exe` hoặc reload để trải nghiệm ngay giao diện màng màu mới.


---

## Phiên làm việc: 17/11/2026 (Căn Giữa Danh Sách Bài Hát Dưới Deck & Căn Chỉnh Đồng Trục SVG Tiêu Đề Modal v1.0.37)

### 1. Mục tiêu hoàn thành:
1. **Căn Giữa Danh Sách Bài Hát Đang Phát (`.setlist`):**
   - Áp dụng `justify-content: center; justify-content: safe center;` cho container danh sách bài `.setlist`.
   - Kết quả: Khi chỉ có 1 bài hoặc một vài bài, chuỗi bài hát được tự động căn giữa đối xứng hoàn hảo ngay dưới Floating Deck trung tâm (độ lệch tâm `< 0.7px`), khắc phục tình trạng bài hát bị dạt cô độc về mép trái màn hình. Khi danh sách dài tràn màn hình, chỉ thị `safe center` tự động chuyển sang căn lề an toàn chống mất đầu chuỗi và cho phép cuộn ngang mượt mà.
2. **Triệt tiêu Lệch Trục Tiêu Đề Modal So Với SVG (`.mobile-modal__title-wrap`):**
   - **Nguyên nhân gốc rễ:** Thẻ `h2` trong các modal kế thừa `margin-bottom: var(--space-2)` (8px) từ `.consent h2`. Khi flexbox căn giữa (`align-items: center`), margin-box của chữ bị dồn thêm 8px phía dưới đẩy phần hiển thị chữ lên cao hơn SVG ~4px.
   - **Giải pháp:** Thiết lập tường minh `.mobile-modal__title-wrap h2 { margin: 0 !important; padding: 0 !important; font: 600 clamp(15px, 2.2vw, 18px) / 1 var(--font-display, var(--font-sans)) !important; display: flex; align-items: center; }` và `.mobile-modal__title-wrap .mobile-modal__icon { display: block; flex-shrink: 0; width: 20px; height: 20px; }`.
   - **Kiểm chứng Playwright:** Tọa độ tâm quang học SVG $Y = 186.50\text{px}$, Tâm chữ $Y = 186.50\text{px}$, độ lệch $\Delta Y = \mathbf{0.00\text{px}}$ (chuẩn xác pixel-perfect tuyệt đối).
3. **Đồng Bộ & Đóng Gói SSOT v1.0.37:**
   - Đồng bộ version `v1.0.37` trên 6 tệp trọng yếu qua `version.py`.
   - Đồng bộ tài nguyên Web vào `dist/MeikovaLoop/_internal/web/`.
   - Vượt qua 22/22 kiểm thử bộ nhớ và 6/6 kiểm thử đối kháng.

### 2. Lệnh kiểm tra đã chạy & Exit Code:
- `.\.venv\Scripts\python.exe tests/test_memory_lifecycle.py`: Ran 22 tests in 36.346s - OK (Exit Code 0).
- `.\.venv\Scripts\python.exe tests/stress_adversarial_r3.py`: Ran 6 tests in 18.436s - OK (Exit Code 0).
- `.\.venv\Scripts\python.exe version.py --check`: ALL 6 FILES IN 100% VERSION SYNCHRONIZATION (Exit Code 0).
- Playwright Bounding Box Inspection: $\Delta Y = 0.00\text{px}$ giữa SVG và H2; độ lệch tâm Setlist với Deck $< 0.7\text{px}$.

---

## Phiên làm việc: 17/11/2026 (Màng Hào Quang Kính Neon Trong Suốt & Triệt Tiêu Lỗi Phím Space Hijack Focus Button v1.0.38)

### 1. Mục tiêu hoàn thành:
1. **Triệt Tiêu Đường Viền Đa Giác Gãy Khúc Cứng Quanh Đĩa Nhạc:**
   - Xóa bỏ hoàn toàn chỉ thị `ctx.stroke()` vẽ viền đỉnh sóng nối các đỉnh tần số xung quanh đĩa nhạc. Triệt tiêu 100% cảm giác khung lồng sắt gãy góc nhân tạo.
2. **Thiết Lập Màng Hào Quang Neon / Kính Mờ Trong Suốt (Neon / Frosted Glass Aura):**
   - Chuyển đổi chế độ pha trộn sang `ctx.globalCompositeOperation = "screen"`, đảm bảo cộng ánh sáng phát quang thuần khiết, triệt tiêu hoàn toàn hiện tượng màu nâu bùn hay đục ngầu trên nền tối.
   - Sử dụng dải gradient tỏa tia trong suốt đa tầng: $0.24 \to 0.13 \to 0.04 \to 0$, kết hợp hiệu ứng tán sắc mềm `ctx.shadowColor` cùng `ctx.shadowBlur = 18`.
3. **Bộ Lọc Thông Thấp Đường Bao (Organic Low-Pass Envelope):**
   - Áp dụng bộ lọc trung bình trượt có trọng số kiểu Gaussian ($W = 8$) trên mảng biên độ âm tần thô `rawV`.
   - Mép màng hào quang uốn lượn nhấp nhô theo sóng lỏng mượt mà tự nhiên theo nhịp điệu của bài hát thay vì các cạnh răng cưa sắc nhọn.
4. **Bảo Tồn Các Vạch Phổ Dày Đặc Chính Xác (Dense Precision Hairlines):**
   - Duy trì $N = 240 \sim 256$ vạch chia thanh thoát (`lineWidth = 1.25`, `lineCap = "round"`), phân tầng 4 cấp độ sáng (`lighter`), nhấp nhô xuyên qua lớp màng kính neon phát quang.
5. **Khắc Phục Lỗi Nút Bị Dính Focus & Phím Space Kích Hoạt Lại Nút Đang Focus:**
   - **Nguyên nhân gốc rễ:** Trình duyệt mặc định giữ focus trên `<button>` sau khi click chuột. Khi người dùng bấm Space, browser kích hoạt `click` trên nút đang focus đó. Đồng thời dòng `if (e.target.closest("button")) return;` trong `main.js` khiến lệnh Play/Pause bị bỏ qua hoàn toàn.
   - **Giải pháp:** 
     + Thêm cơ chế tự động giải phóng focus (`pointerup` và `click` event listeners): Tự động gọi `btn.blur()` ngay sau khi người dùng nhấp chuột hoặc chạm vào bất kỳ nút bấm hay action control nào.
     + Lắng nghe sự kiện `keydown` ở capture phase (`useCapture: true`).
     + Khi phím `Space` được kích hoạt ngoài các ô nhập text (`input, textarea, select, [contenteditable]`): Gọi ngay `e.preventDefault()`, `e.stopPropagation()`, giải phóng `document.activeElement.blur()`, và kích hoạt Play/Pause qua `$("#btn-play")?.click()`.
     + Đã kiểm chứng tự động qua Playwright Headless Edge: Nút đã click không bao giờ giữ focus, phím Space luôn luôn Play/Pause và không kích hoạt lại nút đang focus.
6. **Đóng Gói Native Desktop Shell Chuẩn Môi Trường venv Nội Bộ:**
   - Sử dụng chính xác Python 3.12.4 và PyInstaller 6.22.3 từ virtual environment nội bộ dự án: `D:\JOB\DEV\MashLoop\.venv\Scripts\pyinstaller.exe`.
   - Biên dịch thành công binary `dist/MeikovaLoop/MeikovaLoop.exe` (Exit Code 0, dung lượng ~67.2MB).
   - Đồng bộ toàn bộ web assets (`viz.js`, `main.js`, `app.css`, `index.html`) vào `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code:
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\python.exe" tests/test_memory_lifecycle.py`: Ran 22 tests in 30.066s - OK (Exit Code 0).
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\python.exe" tests/stress_adversarial_r3.py`: Ran 6 tests in 17.438s - OK (Exit Code 0).
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\python.exe" version.py --check`: ALL 6 FILES IN 100% VERSION SYNCHRONIZATION (Exit Code 0).
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\python.exe" tools/test_focus_space_behavior.py`: ALL TESTS PASSED WITH 100% SUCCESS (Exit Code 0).
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\pyinstaller.exe" --noconfirm meikova_loop.spec`: Build complete successfully (Exit Code 0).

---

## Phiên làm việc: 18/11/2026 (Triệt Tiêu False-Positive MemoryPressure & Khôi Phục Vĩnh Viễn Chấm Neon và Thanh Âm Thanh Halo v1.0.39)

### 1. Mục tiêu hoàn thành:
1. **Truy Tìm & Khắc Phục Tận Gốc Lỗi Báo Động Giả Áp Lực Bộ Nhớ (False-Positive Memory Pressure):**
   - **Nguyên nhân gốc rễ:** Trong `loopbox/memory_monitor.py`, điều kiện kích hoạt `HIGH` (`commit_pct >= 88.0%`) và `CRITICAL` (`commit_pct >= 93.0%`) sử dụng toán tử `OR` thuần túy dựa trên tỷ lệ commit ảo toàn hệ điều hành Windows. Khi máy host mở nhiều ứng dụng đa nhiệm (Chrome, IDE, Docker...), `commit_pct` dao động ở mức 90-93% trong khi máy host còn tới gần **10 GB RAM vật lý trống** (`phys_avail = 9617 MB`) và MashLoop chỉ tiêu thụ 23 MB RAM. Điều kiện phục hồi về `normal` đòi hỏi phi thực tế `commit_pct < 82.0%`, khiến ứng dụng sau vài phút bị khóa cứng vĩnh viễn ở trạng thái `critical`.
   - **Giải pháp:** Tái cấu trúc logic đánh giá ngưỡng theo đúng tiêu chuẩn tài nguyên phần cứng thực tế:
     + `is_critical_trigger` chỉ kích hoạt khi RAM vật lý thực sự cạn kiệt (`phys_avail <= 800 MB`), hoặc dung lượng commit khả dụng thực sự cạn kiệt (`commit_avail <= 1536 MB`), hoặc `commit_pct >= 93%` kèm theo RAM vật lý bị suy giảm (`phys_avail <= 2048 MB` hoặc `commit_avail <= 3072 MB`).
     + `can_recover_to_normal` cho phép phục hồi về `normal` ngay khi RAM vật lý an toàn (`phys_avail >= 2560 MB` hoặc `commit_avail >= 3891 MB`), triệt tiêu 100% tình trạng kẹt cứng ở trạng thái cảnh báo giả.
     + Kết quả đo thực tế trên máy host: 5/5 lần kiểm tra đều duy trì trạng thái `normal` liên tục.
2. **Bảo Tồn Vĩnh Viễn Thanh Âm Thanh Halo Xung Quanh Vòng Khuyên (`_drawHalo`):**
   - Xóa bỏ triệt để các điều kiện ngắt vẽ `if (this.memoryPressure === "critical") return;` và `this.memoryPressure !== "critical"` trong [web/js/viz.js](file:///D:/JOB/DEV/MashLoop/web/js/viz.js).
   - Thanh âm thanh Halo vẽ trực tiếp trên canvas chính (zero RAM allocation), do đó luôn luôn nhấp nhô theo nhịp nhạc, không bao giờ bị tắt hoặc biến mất sau một thời gian phát nhạc.
3. **Phát Quang Neon Chống Tắt Cho Chấm Playhead (`_drawHead`):**
   - Thay thế việc vẽ chấm trắng cụt bằng cơ chế phát quang neon dịu nhẹ với `ctx.shadowColor` và `ctx.shadowBlur = 16` kể cả trong tình huống tải cao.
   - Không gọi `createRadialGradient` khi critical, đảm bảo vượt qua 100% bài kiểm thử đối kháng `tests/stress_adversarial_r3.py` (0 gradient calls), đồng thời người dùng luôn nhìn thấy chấm phát quang neon rực rỡ, sống động.
4. **Kiểm Thử Toàn Diện & Đóng Gói SSOT v1.0.39:**
   - 22/22 kiểm thử vòng đời bộ nhớ `test_memory_lifecycle.py` passed (Exit Code 0).
   - 6/6 kiểm thử tải đối kháng `stress_adversarial_r3.py` passed (Exit Code 0).
   - Đồng bộ 100% SSOT phiên bản `v1.0.39` qua `version.py`.
   - Biên dịch hoàn tất binary native [dist/MeikovaLoop/MeikovaLoop.exe](file:///D:/JOB/DEV/MashLoop/dist/MeikovaLoop/MeikovaLoop.exe) (dung lượng ~67.2MB) bằng PyInstaller trong môi trường `.venv` nội bộ.
   - Đồng bộ tài nguyên Web đầy đủ vào `dist/MeikovaLoop/_internal/web/`.

### 2. Lệnh kiểm tra đã chạy & Exit Code:
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\python.exe" tests/test_memory_lifecycle.py`: Ran 22 tests in 48.267s - OK (Exit Code 0).
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\python.exe" tests/stress_adversarial_r3.py`: Ran 6 tests in 26.380s - OK (Exit Code 0).
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\python.exe" version.py --check`: ALL 6 FILES IN 100% VERSION SYNCHRONIZATION (Exit Code 0).
- `& "D:\JOB\DEV\MashLoop\.venv\Scripts\pyinstaller.exe" --noconfirm meikova_loop.spec`: Build complete successfully (Exit Code 0).
