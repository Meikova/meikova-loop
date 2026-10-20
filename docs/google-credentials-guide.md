# Hướng dẫn tạo Google OAuth 2.0 Credentials cho MashLoop

Tài liệu hướng dẫn chi tiết cách thiết lập Google OAuth 2.0 để đăng nhập đồng bộ đa thiết bị (Web & Desktop) cho MashLoop.

---

## 0. Thông số cốt lõi bắt buộc cấu hình

Dù tạo mới hay dùng project có sẵn, khi tạo OAuth Client ID cần điền chính xác:

* **Application Type:** `Web application` *(Bắt buộc chọn Web application để hỗ trợ cả Web GIS và Desktop Loopback)*
* **Authorized JavaScript origins:**
  * `http://localhost:8765`
  * `http://127.0.0.1:8765`
  * *(Tùy chọn nếu deploy Cloud/Hugging Face)*: `https://<ten-space>.hf.space`
* **Authorized redirect URIs:**
  * `http://localhost:8765/api/auth/google/callback`
  * `http://127.0.0.1:8765/api/auth/google/callback`
  * *(Tùy chọn nếu deploy Cloud/Hugging Face)*: `https://<ten-space>.hf.space/api/auth/google/callback`

---

## Hướng 1: Tạo trên Google Cloud Project MỚI (Chưa có sẵn)

### Bước 1: Tạo Project mới
1. Truy cập [Google Cloud Console](https://console.cloud.google.com/).
2. Đăng nhập tài khoản Google của bạn.
3. Ở góc trên cùng bên trái (cạnh logo Google Cloud), nhấn vào menu chọn project -> Chọn **New Project** (Dự án mới).
4. Đặt tên: `MashLoop-Sync` (hoặc tên tùy chọn) -> Nhấn **Create**.
5. Đợi 5-10 giây để Google khởi tạo, sau đó chọn project vừa tạo ở thanh điều hướng trên cùng.

### Bước 2: Thiết lập OAuth Consent Screen (Màn hình đồng ý)
1. Ở thanh menu bên trái, vào **APIs & Services** -> **OAuth consent screen** (Màn hình đồng ý OAuth).
2. Chọn **User Type**: **External** (để tài khoản Gmail bất kỳ đều đăng nhập được) -> Nhấn **Create**.
3. Điền thông tin ứng dụng:
   * **App name:** `MashLoop`
   * **User support email:** Chọn email của bạn.
   * **Developer contact information:** Nhập email của bạn.
   * Nhấn **Save and Continue**.
4. Cấu hình **Scopes** (Phạm vi truy cập):
   * Nhấn **Add or Remove Scopes**.
   * Tích chọn 3 scopes cơ bản:
     * `.../auth/userinfo.email`
     * `.../auth/userinfo.profile`
     * `openid`
   * Nhấn **Update** -> Nhấn **Save and Continue**.
5. Cấu hình **Test users**:
   * Nhấn **Add Users** -> Nhập email Google của bạn (và người thân/bạn bè nếu muốn cho test).
   * Nhấn **Save and Continue** -> Nhấn **Back to Dashboard**.
   * *(Mẹo: Nếu muốn mở cho mọi người không giới hạn, ở màn hình OAuth consent screen, nhấn nút **Publish App** để chuyển sang trạng thái Production)*.

### Bước 3: Tạo OAuth Client ID (Credentials)
1. Ở menu bên trái, chọn **Credentials** (Thông tin xác thực).
2. Nhấn nút **+ CREATE CREDENTIALS** (ở thanh trên cùng) -> Chọn **OAuth client ID**.
3. Cấu hình các trường:
   * **Application type:** Chọn **Web application**.
   * **Name:** `MashLoop Client`.
   * **Authorized JavaScript origins:** Nhấn **+ ADD URI** và thêm:
     * `http://localhost:8765`
     * `http://127.0.0.1:8765`
   * **Authorized redirect URIs:** Nhấn **+ ADD URI** và thêm:
     * `http://localhost:8765/api/auth/google/callback`
     * `http://127.0.0.1:8765/api/auth/google/callback`
4. Nhấn nút **Create**.

### Bước 4: Tải Credentials về máy
1. Sau khi tạo, một hộp thoại hiện ra hiển thị `Client ID` và `Client Secret`.
2. Nhấn nút **DOWNLOAD JSON**.
3. Đổi tên file vừa tải thành `client_secret.json`.

---

## Hướng 2: Tạo trên Google Cloud Project ĐÃ CÓ SẴN

Nếu bạn đã có sẵn project (ví dụ: `titan-remote`, `my-portal`, etc.):

### Bước 1: Chọn Project
1. Vào [Google Cloud Console Credentials](https://console.cloud.google.com/apis/credentials).
2. Nhấp vào dropdown chọn project ở thanh trên cùng và chọn đúng project muốn dùng.

### Bước 2: Kiểm tra OAuth Consent Screen
1. Vào **APIs & Services** -> **OAuth consent screen**.
2. Kiểm tra trạng thái:
   * Nếu đã cấu hình: Đảm bảo danh sách Scopes đã có đủ `email`, `profile`, `openid`.
   * Nếu app đang ở chế độ **Testing**: Cuộn xuống mục **Test users** -> Đảm bảo email bạn dự định đăng nhập đã được thêm vào danh sách.
   * *(Nếu chưa từng cấu hình Consent Screen cho project này, thực hiện như Bước 2 của Hướng 1)*.

### Bước 3: Tạo Credentials mới hoặc Cập nhật Client ID cũ
Bạn có 2 lựa chọn:

#### Cách A: Tạo Client ID riêng cho MashLoop (Khuyên dùng)
1. Vào **APIs & Services** -> **Credentials**.
2. Nhấn **+ CREATE CREDENTIALS** -> Chọn **OAuth client ID**.
3. Application type: **Web application**.
4. Name: `MashLoop Desktop & Web`.
5. Thêm các Origins và Redirect URIs như mục **0. Thông số cốt lõi** ở trên.
6. Nhấn **Create** -> Nhấn **DOWNLOAD JSON** -> Đổi tên thành `client_secret.json`.

#### Cách B: Dùng lại Client ID Web đã có sẵn
1. Trong danh sách **OAuth 2.0 Client IDs**, nhấn vào biểu tượng **Sửa (cây bút)** của Client ID bạn muốn dùng lại.
2. Tại mục **Authorized JavaScript origins**, nhấn **+ ADD URI** và điền thêm:
   * `http://localhost:8765`
   * `http://127.0.0.1:8765`
3. Tại mục **Authorized redirect URIs**, nhấn **+ ADD URI** và điền thêm:
   * `http://localhost:8765/api/auth/google/callback`
   * `http://127.0.0.1:8765/api/auth/google/callback`
4. Nhấn **Save** ở cuối trang.
5. Nhấn nút tải về (mũi tên download) ở hàng của Client ID đó -> Đổi tên thành `client_secret.json`.

---

## Cách đưa Credentials vào MashLoop

Hệ thống MashLoop hỗ trợ 3 tầng Fallback thông minh:

### Cách 1: Nạp file JSON (Cho Local Dev & Desktop) - Khuyên dùng
Copy file `client_secret.json` đã tải về đặt vào một trong hai thư mục:
* `data/client_secret.json` (thư mục này đã có trong `.gitignore`, an toàn không lo commit nhầm).
* Thư mục gốc project: `MashLoop/client_secret.json`.

### Cách 2: Nạp biến môi trường (Cho Cloud / Hugging Face Spaces / Render)
Lấy trực tiếp chuỗi `Client ID` và `Client Secret` từ file JSON hoặc giao diện Google Console:
* Tạo file `.env` ở thư mục gốc:
  ```env
  GOOGLE_CLIENT_ID=515668723869-xxxxxxxx.apps.googleusercontent.com
  GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxx
  ```
* Hoặc trên Hugging Face Spaces: Vào **Settings** -> **Variables and secrets** -> Thêm Secret `GOOGLE_CLIENT_SECRET` và Variable `GOOGLE_CLIENT_ID`.

### Cách 3: Zero-Setup CI/CD (Tự động)
Nếu không có file và không có biến môi trường, MashLoop đã tích hợp sẵn chuỗi Base64 dự phòng trong `loopbox/auth.py`, cho phép file `.exe` chạy được ngay lập tức mà không cần cấu hình thêm.
