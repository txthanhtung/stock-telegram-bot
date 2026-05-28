import pandas as pd
import requests
import datetime
import schedule
import time

# ================= CẤU HÌNH BAN ĐẦU =================
TELEGRAM_TOKEN = '7798428152:AAG7chT7vwobu7ccMaXsONoGbEYjcxHodWU'
CHAT_ID = '5452985380'
TICKERS = ['FPT', 'HPG', 'SSI', 'MWG'] 

# ================= TƯƠNG THÍCH VNSTOCK V3 & V4 =================
try:
    # Thử import theo chuẩn hướng đối tượng mới của Vnstock V4.x
    from vnstock import Vnstock
    vnstock_client = Vnstock()
    use_v4 = True
    print("✨ Đã phát hiện và cấu hình tương thích cho Vnstock V4.x")
except ImportError:
    # Nếu không có V4, fallback về cách import truyền thống của V3.x
    from vnstock import stock_historical_data
    use_v4 = False
    print("✨ Đã phát hiện và cấu hình tương thích cho Vnstock V3.x")

def get_historical_data_compatible(ticker, start_date, end_date):
    """Hàm lấy dữ liệu lịch sử tương thích cho cả Vnstock V3 và V4"""
    if use_v4:
        # Cú pháp lấy dữ liệu chuẩn của Vnstock 4.x
        try:
            # Khởi tạo đối tượng stock cho mã chứng khoán với nguồn cấp VCI (Vietcap) thay vì TCBS
            stock = vnstock_client.stock(symbol=ticker, source='VCI')
            # Lấy lịch sử giá
            return stock.quote.history(start=start_date, end=end_date)
        except Exception as e:
            print(f"Lỗi lấy dữ liệu V4 cho {ticker}: {e}")
            return None
    else:
        # Cú pháp của Vnstock V3 trở xuống
        return stock_historical_data(
            symbol=ticker, 
            start_date=start_date, 
            end_date=end_date, 
            resolution='1D', 
            type='stock'
        )

# ================= TÍNH TOÁN CHỈ BÁO & GỬI TIN =================
def send_telegram(message):
    """Hàm gửi tin nhắn báo động về Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Đã gửi tin nhắn Telegram thành công!")
        else:
            print(f"❌ Lỗi API Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Lỗi kết nối Telegram: {e}")

def calculate_rsi(df, period=14):
    """Tính toán chỉ số RSI tự chế bằng Pandas gốc"""
    delta = df['close'].diff()
    gain = (delta.clip(lower=0))
    loss = (-delta.clip(upper=0))
    
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def analyze_and_alert(ticker):
    """Hàm tải dữ liệu lịch sử, tính RSI và lọc điều kiện mua"""
    now = datetime.datetime.now()
    start_date = (now - datetime.timedelta(days=100)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')
    
    try:
        # Lấy dữ liệu thông qua hàm tương thích thông minh
        df = get_historical_data_compatible(ticker, start_date, end_date)
        
        if df is None or df.empty:
            print(f"⚠️ Không có dữ liệu cho mã: {ticker}")
            return

        # Đồng bộ toàn bộ tên cột thành chữ thường để tránh lỗi lệch pha giữa V3 và V4
        df.columns = [col.lower() for col in df.columns]

        # Sắp xếp lại dữ liệu theo thời gian tăng dần
        if 'time' in df.columns:
            df = df.sort_values(by='time').reset_index(drop=True)
        elif 'date' in df.columns:
            df = df.sort_values(by='date').reset_index(drop=True)

        # Tính toán RSI 14 phiên
        df['rsi_14'] = calculate_rsi(df, period=14)
        
        # Lấy dữ liệu của phiên mới nhất
        latest_data = df.iloc[-1]
        close_price = latest_data['close']
        rsi_14 = latest_data['rsi_14']
        
        # Kiểm tra điều kiện mua (RSI <= 35)
        if rsi_14 <= 35:
            msg = f"🟢 **TÍN HIỆU MUA: {ticker}**\n" \
                  f"💰 Giá đóng cửa: {close_price:,} VND\n" \
                  f"📊 RSI(14): {rsi_14:.2f} (Quá bán - Cơ hội tích lũy)"
            send_telegram(msg)
            print(f"👉 Đã phát hiện và gửi tín hiệu mua cho {ticker} (RSI: {rsi_14:.2f})")
        else:
            print(f"ℹ️ {ticker}: RSI hiện tại là {rsi_14:.2f} (Chưa vào vùng quá bán)")
            
    except Exception as e:
        print(f"❌ Gặp lỗi khi xử lý mã {ticker}: {e}")

def job():
    print(f"\n--- [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bắt đầu quét thị trường ---")
    for t in TICKERS:
        analyze_and_alert(t)
    print("--- Hoàn tất lượt quét ---")

# ================= BẮT ĐẦU CHẠY HỆ THỐNG =================
if __name__ == "__main__":
    print("🚀 Khởi động Bot Telegram Chứng khoán tự động quét...")
    
    # Gửi tin nhắn test ngay khi bật tool để kiểm tra kết nối Telegram
    print("Đang kiểm tra kết nối tới Telegram...")
    send_telegram("🤖 *Stock Bot đã khởi động thành công!*\nĐang tiến hành quét tín hiệu các mã: " + ", ".join(TICKERS))
    
    print("Đang chạy thử lần đầu tiên để kiểm tra tín hiệu cổ phiếu...")
    job() # Chạy thử ngay lập tức khi khởi động
    
    # Hẹn giờ chạy tự động mỗi ngày lúc 14:00 (giờ Việt Nam)
    schedule.every().day.at("14:00").do(job)
    
    print("\nBot đang chạy ngầm và chờ đến 14:00 mỗi ngày để quét...")
    while True:
        schedule.run_pending()
        time.sleep(1)