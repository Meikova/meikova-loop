---
title: Meikova Loop
emoji: loop
colorFrom: blue
colorTo: pink
sdk: gradio
sdk_version: 6.30.0
python_version: '3.12'
app_file: app.py
pinned: false
license: mit
---

# Meikova Loop

<div align="center">

<img src="docs/assets/logo.png" alt="Meikova Loop Logo" width="160px">

[![Release](https://img.shields.io/github/v/release/Meikova/meikova-loop?style=flat-square&color=059669)](https://github.com/Meikova/meikova-loop/releases)
[![Platforms](https://img.shields.io/badge/Platforms-Web%20%7C%20Desktop%20%7C%20Mobile%20PWA%20%7C%20Docker-2563eb?style=flat-square)](https://github.com/Meikova/meikova-loop)
[![Python](https://img.shields.io/badge/Python-3.12-3b82f6?style=flat-square)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-Turso%20libSQL-00e699?style=flat-square)](https://turso.tech/)
[![Security](https://img.shields.io/badge/Security-OWASP%20Hardened-emerald?style=flat-square)](https://owasp.org/)
[![License](https://img.shields.io/badge/License-MIT-16a34a?style=flat-square)](LICENSE)

**Động cơ DJ mashup và infinite soundscape phát nhạc vô tận, tự động phân tích beat, tách stem, nắn tempo, chuyển bài thông minh, bảo mật cấp độ doanh nghiệp và tích hợp Universal SSO.**

[Trải Nghiệm Trực Tuyến](https://m3ik18dp-meikova-loop.hf.space) | [Tải Bản Desktop](https://github.com/Meikova/meikova-loop/releases) | [Báo Lỗi](https://github.com/Meikova/meikova-loop/issues)

</div>

---

> [!NOTE]
> **Thông tin Fork & Bản quyền Tác giả Gốc:**
> - **Tác giả gốc (Original Author):** **Truc** ([@lvt1693](https://github.com/lvt1693))
> - **Kho mã nguồn gốc (Original Repository):** [https://github.com/lvt1693/mashloop](https://github.com/lvt1693/mashloop)
> - **Trang web chính thức của tác giả:** [https://mashloop.truclv.com](https://mashloop.truclv.com)
> - **Bản fork phát triển bởi:** **Phạm Đoàn Kiếm** ([@m3iK18dp](https://github.com/m3iK18dp))
> - **Bản web trực tuyến (Hugging Face Spaces):** [https://m3ik18dp-meikova-loop.hf.space](https://m3ik18dp-meikova-loop.hf.space)
>
> **Các tính năng mở rộng chuyên sâu trong bản fork này:**
> 1. **Windows Desktop Native Shell:** Đóng gói độc lập qua PyInstaller & Microsoft Edge WebView2, tiêu đề Dark Mode Win11 frameless custom titlebar, khởi động 1-click.
> 2. **ONNX Inference & Tối ưu VRAM GPU:** Chuyển đổi mô hình Beat This! sang ONNX Runtime; cơ chế Demucs streaming theo từng chunk 7.8s giúp card đồ họa 4GB VRAM (như GTX 1650 Ti) chạy mượt mà không bị tràn bộ nhớ CUDA.
> 3. **Hệ thống Bảo mật OWASP Hardening:** 5-Strike Lockout chống brute-force đăng nhập, vô hiệu hóa IDOR session spoofing, triệt tiêu LFI/SSRF (chặn schema `file://` và dải IP private/link-local/cloud metadata), bảo vệ ranh giới Host Client cho các API hạ tầng, bổ sung đầy đủ HTTP Security Headers, Ed25519 Universal SSO không hardcode key.
> 4. **Mobile Shell & Tailscale Mesh Streaming:** Hỗ trợ kết nối mượt qua mạng riêng ảo Tailscale, bộ icon PWA/Retina siêu nét cho iOS/Android, xử lý Safe-Area tai thỏ/Dynamic Island, tích hợp MediaSession API phát nhạc nền.
> 5. **Turso Cloud DB & Offline Data Sync:** Hỗ trợ lưu trữ offline SQLite cục bộ kết hợp đồng bộ hóa thư viện qua libSQL/Turso cloud.
> 6. **Cloudflare Quick Tunnel Bridge:** Tích hợp sẵn `trycloudflare.com` khởi động 1-click, chia sẻ phiên nghe ra toàn cầu mà không cần mở cổng NAT/Router.
> 7. **Zero-Profile-Pollution:** Gom toàn bộ dữ liệu cấu hình, database và cache vào `%LOCALAPPDATA%\MeikovaLoop` trên Windows hoặc `~/.meikova-loop` trên Linux/macOS.
> 8. **The Deck & Tiện ích Nghe nhạc:** Hẹn giờ tắt nhạc (Sleep Timer) có làm dịu âm lượng thông minh trong 8s cuối, nút Khóa bài (`L`), Lọc âm đêm dịu tai High-Shelf EQ (`E`), Tắt tiếng nhanh (`M`), Bảng phím tắt & Trợ giúp (`?`).

---

Bài hay thường hết quá sớm. Meikova Loop sửa lỗi đó.

- **Trải nghiệm trực tuyến (Hugging Face Space):** [https://m3ik18dp-meikova-loop.hf.space](https://m3ik18dp-meikova-loop.hf.space)
- **Nghe thử bản gốc:** [https://mashloop.truclv.com](https://mashloop.truclv.com)

Meikova Loop nghe kỹ từng beat của bài hát rồi phát mãi không dứt. Trong một bài, nó nhảy qua lại giữa những đoạn tương đồng đến mức khó nhận ra đang ở lần lặp thứ mấy. Phần cốt lõi là ở **giữa các bài**: khi đã ở đủ lâu, hệ thống tìm chỗ nối sang bài khác, khớp nhịp, nắn tempo, giữ mood, rồi mix chuyển tiếp như một set DJ liên tục. Mỗi bài đại diện cho một vòng của dấu vô cực mang màu sắc theo tâm trạng (mood) bài đó.

## Nó làm gì

- **Mash cả thư viện thành một chuỗi.** Không chỉ lặp trong một bài như [Infinite Jukebox](https://musicmachinery.com/2012/11/12/the-infinite-jukebox/) ngày xưa: ở mỗi bài một lúc, rồi đi tới điểm nối tốt gần nhất sang bài khác.
- **Mười ba kiểu nối bài và mười cách blend**, từ nối thẳng không lộ tới mashup kiểu DJ (bảng bên dưới). Bật tắt từng kiểu trong *Tinh chỉnh*.
- **Nắn tempo mà giữ tông (key lock).** Lệch tới 8 % vẫn blend được, kể cả nhịp đôi 70 ↔ 140, và giọng ca sĩ không bị bổng hay trầm đi. Lệch xa hơn (tới 18 %) thì bài trước kéo tempo dần về phía bài sau. Hai bài lệch tông thì bài sau được dịch tới hai nửa cung cho hợp, rồi trượt dần về tông gốc.
- **Nối vào đúng đoạn:** ra ở cuối câu nhạc, vào đầu điệp khúc hay chỗ drop của bài sau, không chỉ vào đầu bài.
- **Chọn tiêu chí cho bài kế tiếp:** cân bằng, cùng mood, cùng nhịp, hợp tông (vòng Camelot của DJ), như một set DJ (khởi động, lên dần tới đỉnh, cứ vài bài lại có một khoảng nghỉ rồi lên lại), hoặc tự do. Tiêu chí nào cũng nhìn trước một bước: không chọn bài mà từ đó chỉ còn cách crossfade đi tiếp.
- **Biết ai đang hát:** không nhảy từ giọng nam sang giọng nữ giữa câu, không cắt ngang một câu hát, không để hai giọng hát chồng nhau. Có stem giọng hát riêng nên blend được chỉ phần nhạc, hoặc để giọng bài sau hát trên nền bài trước.
- **Mỗi bài một màu theo mood**, cả căn phòng đổi màu theo bài đang phát và chuyển dần sang màu bài sau trong lúc mix. Có quầng phổ âm thanh quanh vòng đang phát. Thích yên tĩnh thì chọn Neon hoặc Hổ phách trong *Tinh chỉnh*.
- **Nhiều nguồn:** link YouTube (cả playlist), SoundCloud, Bandcamp, Zing MP3, Mixcloud; gõ tên bài để tìm trên YouTube; hoặc thả file nhạc, cả nguyên file zip.

## Các kiểu nối bài

| Kiểu | Khi nào | Nghe ra sao |
|---|---|---|
| Nối thẳng | Hai đoạn nghe gần như y hệt nhau | Không nhận ra là đã đổi bài |
| Drop | Cùng groove, cùng cường độ, cùng mood | Bài mới vào đúng phách đầu câu nhạc |
| Blend | Nhịp khớp được (lệch tới 8 %, kể cả nhịp đôi 70 ↔ 140) | Mix kiểu DJ, khóa nhịp từng beat, 2 đến 32 ô nhịp |
| Crossfade dài | Hai bài khác mood | 5 đến 11 giây, lọc âm: bài cũ tối dần, bài mới sáng dần |
| Echo | Cuối một câu hát | Bài cũ tan thành tiếng vọng của chính nó |
| Wash | Cuối một đoạn | Bài cũ chìm vào reverb, bài mới bước ra từ đó |
| Build-up | Vào một đoạn drop hay điệp khúc | Bài cũ mỏng dần dưới tiếng gió dâng lên, bài mới nổ vào cùng một cú impact |
| Flanger | Cuối một câu | Bài cũ quét tiếng phản lực rồi đi |
| Ngắt lặng | Bài cũ đang to, bài mới vào mạnh | Im đúng một nhịp, rồi bài mới vào trên phách mạnh |
| Phanh đĩa, cuộn nhịp, spinback, gate | Khi bạn muốn | Đột ngột. Tắt sẵn, bật trong *Tinh chỉnh* nếu thích kịch tính |

Mười cách blend: dài, đổi EQ (bass, mid, treble lần lượt), ngắn, quét filter, đổi chỗ ở drop, trao giọng (tách giọng), acapella (giọng bài sau hát trên nền bài trước, nhạc bài sau lên dần bên dưới), mashup (như acapella nhưng trọn 16–32 ô nhịp), double drop (hai đoạn drop nổ cùng lúc), và vòng lặp (lặp vài ô nhịp bài trước làm outro cho những bài không có outro).

Khi hai bài lệch tempo, bài sau vào đúng tốc độ bài trước rồi trượt dần về tốc độ gốc, giữ nguyên tông nhờ time-stretch. Hai bài lệch tông hẳn thì không blend, hai bộ trống chưa khớp nhịp thì không crossfade chồng lên nhau.

## Dùng bản trên web

- **Bản trực tuyến (Hugging Face Spaces):** [https://m3ik18dp-meikova-loop.hf.space](https://m3ik18dp-meikova-loop.hf.space)
- **Bản gốc của tác giả:** [https://mashloop.truclv.com](https://mashloop.truclv.com)

Mỗi lần mở trang là một thư viện mới, trống trơn, của riêng bạn. Chưa biết thêm gì thì mở một trong 9 kho có sẵn: Pass The Aux (làm bằng Suno), Pop, Rock, Hip-hop, Electro & Dance, Chill & Lofi, Acoustic, Remix ccMixter, Kevin MacLeod. Tám kho sau là nhạc Creative Commons từ Jamendo, ccMixter và Incompetech, có ghi tên tác giả. Nghe hết một kho thì nó tự nối sang kho kế, hoặc bấm *Kho khác*.

- Mỗi thư viện tối đa 10 bài tự thêm. Bài người khác đã thêm trước đó thì vào ngay, không phải chờ phân tích; bài mới mất chừng 20 giây.
- File âm thanh không ai nghe trong 12 giờ thì tự xoá. Trang không lưu dữ liệu cá nhân nào, và là dự án phi thương mại.
- Bấm lên vòng để phát từ đoạn đó (vào ngay ở nhịp kế tiếp, không lệch nhịp). Rê chuột lên một chấm bên ngoài vòng để xem nó dẫn tới bài nào, bấm để tự chọn điểm chuyển. `Space` phát / dừng, `J` nhảy ngay, `N` sang bài khác.

## Chạy trên máy cá nhân

Đã thử nghiệm tối ưu trên Windows 11 với Python 3.12+ và card NVIDIA GPU. Nếu không có GPU rời, hệ thống tự động chuyển sang CPU inference mượt mà.

Yêu cầu tiên quyết: Python 3.11+, [ffmpeg](https://ffmpeg.org/) trong `PATH`, và [Node.js](https://nodejs.org/) 20+.

```powershell
python -m venv .venv
.venv\Scripts\pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
.venv\Scripts\pip install --no-deps beat-this demucs
.venv\Scripts\pip install -r requirements.txt
.\run.ps1          # mở http://127.0.0.1:8765, tự dọn dẹp tiến trình cũ
```

Lần phân tích đầu tiên sẽ tải model Beat This! và Demucs (khoảng 160 MB). Chạy trên máy cá nhân: thư viện được lưu trữ vĩnh viễn, không giới hạn số bài.

Sử dụng giao diện dòng lệnh (CLI):

```powershell
.venv\Scripts\python -m loopbox.cli add "Daft Punk Get Lucky audio" "https://www.youtube.com/playlist?list=..."
.venv\Scripts\python -m loopbox.cli list
.venv\Scripts\python -m loopbox.cli rejump     # tính lại điểm nhảy từ dữ liệu đã lưu
.venv\Scripts\python -m loopbox.cli relink     # tính lại điểm nối giữa các bài
```

## Chạy bằng Docker

Dự án hỗ trợ chạy container độc lập 100% qua Docker và Docker Compose, cài đặt sẵn toàn bộ runtime Python, Deno, FFmpeg và cloudflared:

```bash
# Khởi chạy dịch vụ container
docker compose up -d

# Xem log trực tiếp
docker compose logs -f

# Mở Cloudflare Quick Tunnel ra Internet xuyên NAT/Firewall
AUTO_TUNNEL=1 docker compose up -d
```

Dịch vụ chạy tại cổng 8765 (truy cập `http://localhost:8765`).

## Đường hầm Cloudflare Quick Tunnel

Tích hợp sẵn Cloudflare Quick Tunnel (`trycloudflare.com`) cho phép mở link công khai chia sẻ set nhạc tức thì mà không cần mở port mạng:

- **Khởi động kèm Tunnel:** `python app.py --tunnel` (hoặc `AUTO_TUNNEL=1` trong Docker)
- **Quản trị API:**
  - `GET /api/tunnel/status` - Lấy link https://*.trycloudflare.com
  - `POST /api/tunnel/start` - Bật đường hầm
  - `POST /api/tunnel/stop` - Tắt đường hầm
  - `POST /api/tunnel/restart` - Khởi động lại đường hầm

## Kiến trúc Phòng thủ & Bảo mật (OWASP Hardening)

Meikova Loop áp dụng các chuẩn an ninh nghiêm ngặt nhất:

1. **5-Strike Lockout:** Cơ chế khóa tạm thời (15 phút) địa chỉ IP hoặc định danh đăng nhập khi nhập sai thông tin 5 lần liên tiếp, chống tấn công dò mật khẩu (brute-force).
2. **Artificial Delay:** Thêm độ trễ ngẫu nhiên (300-350ms) trong quy trình xác thực thất bại, triệt tiêu tấn công dựa trên thời gian thực thi (timing attacks).
3. **Chống IDOR Session Hijacking:** Kiểm soát chặt chẽ quyền truy cập thư viện qua JWT Token đã xác thực; cấm mạo danh session qua header `X-Session: u_*`.
4. **Triệt tiêu LFI & SSRF:** Chặn tuyệt đối URI schema `file://`. Phân giải DNS và lọc triệt để các dải IP nội bộ, loopback (`127.0.0.1`), link-local, và endpoint metadata của cloud provider (`169.254.169.254`).
5. **Host Boundary Guard:** Các endpoint quản trị nhạy cảm (`/api/tunnel/*`, `/api/cookies`, `/api/settings`) chỉ chấp nhận yêu cầu từ localhost/desktop shell hoặc header `X-Admin-Key` hợp lệ.
6. **Security Headers:** Tích hợp sẵn `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`.
7. **Universal SSO Ed25519:** Chữ ký số phân tán tốc độ cao (0.1ms verification) không chứa fallback key tĩnh có thể suy đoán.

## Dựng cho nhiều người (Multi-User)

Đặt `MEIKOVA_LOOP_MULTIUSER=1` là thành bản cho nhiều người: mỗi lượt truy cập một thư viện riêng, bài hát và điểm nối giữa từng cặp bài là kho chung trên server. Thư mục `deploy/` có đủ cấu hình để dựng trên Ubuntu có GPU:

- `pack.py` đóng gói code, `setup.sh` cài venv, deno và service systemd (app chỉ nghe trên `127.0.0.1`).
- `haproxy.cfg` và `haproxy-setup.sh`: HAProxy đứng trước, TLS bằng Let's Encrypt tự gia hạn.
- `seed_samples.py`: biến một file zip nhạc thành thư viện mẫu. `seed_cc.py`: dựng các kho nhạc Creative Commons từ Jamendo, ccMixter và Incompetech.
- `meikova-loop.service`: số bài phân tích song song, giới hạn mỗi thư viện, dung lượng kho nhạc, tất cả cấu hình qua biến môi trường.

## Bên trong

Mỗi bài đi qua dây chuyền phân tích âm nhạc chuyên sâu (`loopbox/analysis/`):

1. **Beat This!** dò beat và downbeat. Model trả về theo lưới 20 ms; một bước tinh chỉnh kéo từng beat về đúng đỉnh onset, độ lệch chỉ còn khoảng 0.7 ms.
2. **Demucs** tách trống, bass, giọng hát và nhạc cụ đệm.
3. Mỗi beat được mô tả bằng hòa âm (lấy từ phần không có trống), âm sắc, độ lớn, nhịp điệu bên trong beat, mức của từng stem, và giọng hát: cao độ cùng âm sắc của riêng stem vocal. Mood của cả bài (năng lượng, độ tươi) suy ra từ trống, tempo, độ sáng và trưởng/thứ.
4. Key đoán bằng profile Albrecht-Shanahan trên stem hòa âm và bass. Đoạn và câu nhạc tìm từ ma trận tự tương đồng.
5. Điểm nhảy là cặp beat mà cả cửa sổ 8 beat quanh chúng khớp nhau, cùng vị trí trong câu nhạc 4 ô nhịp, có crossfade riêng cho từng chỗ (12 ms nếu trống chắc, tới 60 ms nếu là nốt ngân).
6. Điểm nối giữa hai bài được tìm và lưu cho từng cặp; một cặp chỉ tính một lần cho tất cả người dùng.

Bộ phát (`web/js/`) vận hành trên Web Audio API thuần, lên lịch trước 0.6 giây và chính xác tới từng sample âm thanh. Đường tới điểm chuyển bài được tối ưu bằng thuật toán Dijkstra trên đồ thị beat.

## Kiểm tra chất lượng

Bộ kiểm thử tự động toàn diện:

```powershell
# Chạy bộ test bảo mật OWASP Hardening
.venv\Scripts\python -m unittest tests.test_loop_security_hardening

# Chạy toàn bộ 38 test suites (Authentication, Hydration, Rate Limit, Library...)
.venv\Scripts\python -m unittest discover tests

# Mô phỏng set phát DJ không ngắt quãng
node tools\sim_player.mjs 180 chain
```

## Bản quyền & Ghi công

Repo này không chứa bất kỳ file nhạc nào. Nhạc tải về nằm trong thư mục dữ liệu cục bộ và không đi đâu cả. Dùng cho mục đích cá nhân, tôn trọng điều khoản của các nền tảng âm nhạc và quyền của nghệ sĩ.

Cảm ơn [The Infinite Jukebox](https://musicmachinery.com/2012/11/12/the-infinite-jukebox/) của Paul Lamere và [Eternal Jukebox](https://github.com/EternalBox/EternalJukebox) đã khởi xướng ý tưởng. Trọng tâm thuật toán dựa trên [Beat This!](https://github.com/CPJKU/beat_this), [Demucs](https://github.com/facebookresearch/demucs), [librosa](https://librosa.org/) và [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## License

[MIT](LICENSE). Áp dụng cho mã nguồn trong repository này.

## Hệ sinh thái Meikova

- [Meikova Harvest](https://github.com/Meikova/meikova-harvest) - Hệ sinh thái trích xuất và tải đa phương tiện đa nền tảng.
- [Meikova Loop](https://github.com/Meikova/meikova-loop) - DJ mashup và infinite soundscape engine chạy trên web, desktop và mobile.
- [Meikova Relay](https://github.com/Meikova/meikova-relay) - Điều khiển máy tính từ xa độ trễ thấp, outbound-only.
- [Meikova Auth](https://github.com/Meikova/meikova-auth) - Cổng xác thực tập trung, Universal SSO Ed25519 và quản lý danh tính đa nền tảng.
- [Meikova Balance](https://github.com/Meikova/meikova-balance) - Quản lý tài chính cá nhân, chia hóa đơn nhóm và trợ lý AI đa tầng.
- [Meikova Campus](https://github.com/Meikova/meikova-campus) - Nền tảng thương mại khóa học, phân quyền Google Drive tự động và LMS trực tuyến.
- [Meikova Exchange](https://github.com/Meikova/meikova-exchange) - Sàn giao dịch B2B cho dự án phần mềm, mã nguồn và tài sản số.
- [Meikova Traverse](https://github.com/Meikova/meikova-traverse) - Trình duyệt tệp tin cục bộ, SFTP, WebDAV và quản lý lưu trữ đa nền tảng.
- [Meikova Shield](https://github.com/Meikova/meikova-shield) - Hệ thống phòng thủ an ninh mạng và phát hiện web defacement bằng học máy lai ghép.
- [Meikova Vision](https://github.com/Meikova/meikova-vision) - Bộ công cụ xử lý ảnh RAW, ghép đa phơi sáng HDR và tone mapping chuyên nghiệp.
- [Meikova Flow](https://github.com/Meikova/meikova-flow) - Động cơ trích xuất, biến đổi, nạp dữ liệu (ETL) và tự động hóa luồng báo cáo.
