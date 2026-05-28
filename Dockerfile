# Sử dụng Python 3.11 (Phiên bản cực kỳ ổn định cho vnstock và pandas)
FROM python:3.11-slim

# Đặt thư mục làm việc trong container
WORKDIR /app

# Thiết lập múi giờ mặc định cho môi trường Container (Giờ VN)
ENV TZ=Asia/Ho_Chi_Minh

# Copy file requirements.txt vào và cài đặt thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY . .

# Lệnh chạy script ngầm khi container khởi động
CMD ["python", "-u", "main.py"]