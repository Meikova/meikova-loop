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
