import pandas as pd
import datetime
import schedule
import time
import threading
import telebot

# ================= CẤU HÌNH BAN ĐẦU =================
TELEGRAM_TOKEN = '7798428152:AAG7chT7vwobu7ccMaXsONoGbEYjcxHodWU'
CHAT_ID = '5452985380' # Dùng để nhận báo cáo tự động lúc 15:00
TICKERS = ['HPG', 'VEA', 'VCB', 'BID', 'CTG', 'TCB', 'MBB', 'VPB', 'ACB', 'STB', 
    'SHB', 'TPB', 'HDB', 'VIB', 'LPB', 'MSB', 'OCB', 'EIB', 'SSB',"REE"] 

# Khởi tạo Bot Telegram
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ================= TƯƠNG THÍCH VNSTOCK V3 & V4 =================
try:
    # Gọi thư viện theo chuẩn kiến trúc mới của Vnstock 4.0.1+
    from vnstock.api.quote import Quote
    print("✨ Đã kết nối thư viện vnstock.api mới nhất!")
except ImportError:
    print("❌ Thư viện chưa cập nhật. Vui lòng chạy lệnh: pip install vnstock -U")

def get_historical_data(ticker, start_date, end_date):
    """Hàm lấy dữ liệu lịch sử chuẩn vnstock mới với cơ chế chống lỗi 400"""
    try:
        q = Quote(symbol=ticker, source='VCI')
        return q.history(start=start_date, end=end_date)
    except Exception as e:
        print(f"⚠️ Nguồn VCI gặp lỗi ({e}). Tự động chuyển nguồn cho {ticker}...")
        try:
            q_fallback = Quote(symbol=ticker, source='TCBS')
            return q_fallback.history(start=start_date, end=end_date)
        except Exception as e_fallback:
            print(f"❌ Cả 2 nguồn đều lỗi không lấy được dữ liệu {ticker}: {e_fallback}")
            return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.clip(lower=0)).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

# ================= HÀM PHÂN TÍCH LÕI =================
def analyze_stock(ticker, reply_chat_id=None, waiting_msg_id=None):
    """
    Bổ sung waiting_msg_id để bot cập nhật trực tiếp vào tin nhắn chờ "Đang phân tích..."
    """
    now = datetime.datetime.now()
    start_date = (now - datetime.timedelta(days=200)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')
    
    try:
        df = get_historical_data(ticker, start_date, end_date)
        if df is None or df.empty:
            if reply_chat_id and waiting_msg_id:
                bot.edit_message_text(f"⚠️ Không tìm thấy dữ liệu cho mã: <b>{ticker}</b>", 
                                      chat_id=reply_chat_id, message_id=waiting_msg_id, parse_mode='HTML')
            return

        df.columns = [col.lower() for col in df.columns]
        time_col = 'time' if 'time' in df.columns else 'date'
        
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(by=time_col).reset_index(drop=True)

        # 1. Tính EMA 50 & Volume Trung bình
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['avg_vol_20'] = df['volume'].rolling(window=20).mean()
        
        # 2. Tính RSI 14
        df['rsi_14'] = calculate_rsi(df['close'], period=14)
        
        # 3. Tính MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_line'] = ema_12 - ema_26
        df['signal_line'] = df['macd_line'].ewm(span=9, adjust=False).mean()
        
        # Bắt lỗi thiếu dữ liệu
        if len(df) < 51:
            if reply_chat_id and waiting_msg_id:
                bot.edit_message_text(f"⚠️ <b>{ticker}</b> chưa đủ dữ liệu lịch sử để phân tích.", 
                                      chat_id=reply_chat_id, message_id=waiting_msg_id, parse_mode='HTML')
            return

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Kiểm tra chống lỗi NaN (cổ phiếu vừa lên sàn bị rỗng dữ liệu)
        if pd.isna(curr['ema_50']) or pd.isna(curr['rsi_14']):
            if reply_chat_id and waiting_msg_id:
                bot.edit_message_text(f"⚠️ Mã <b>{ticker}</b> có dữ liệu lịch sử bị lỗi, không thể tính toán.", 
                                      chat_id=reply_chat_id, message_id=waiting_msg_id, parse_mode='HTML')
            return
        
        # --- BỘ LOGIC CẢNH BÁO TRUNG HẠN ---
        msg = None
        
        # LUỒNG 1: PULLBACK (Mua khi điều chỉnh)
        if (curr['close'] > curr['ema_50']) and \
           ((prev['rsi_14'] <= 40 and curr['rsi_14'] > 40) or (prev['rsi_14'] <= 50 and curr['rsi_14'] > 50)) and \
           (curr['volume'] > curr['avg_vol_20']):
            msg = f"🟢 <b>[TÍN HIỆU CÓ THỂ MUA] KẾT THÚC ĐIỀU CHỈNH: {ticker}</b>\n" \
                  f"💰 Giá: {curr['close']:,} (Trên EMA 50)\n📊 RSI(14) vừa cắt lên: {curr['rsi_14']:.2f}\n🌊 Dòng tiền vào mạnh."
                  
        # LUỒNG 2: BẮT ĐÁY
        elif (prev['rsi_14'] <= 30 and curr['rsi_14'] > 30) and \
             (prev['macd_line'] <= prev['signal_line'] and curr['macd_line'] > curr['signal_line']) and \
             (curr['close'] > curr['open']):
            msg = f"🟢 <b>[TÍN HIỆU CÓ THỂ MUA] CHÂN SÓNG ĐẢO CHIỀU: {ticker}</b>\n" \
                  f"💰 Giá: {curr['close']:,} (Nến xanh)\n📊 RSI(14) thoát 30: {curr['rsi_14']:.2f}\n📈 MACD cắt lên Signal."
                  
        # LUỒNG 3: CẮT LỖ / BÁN
        elif (curr['close'] < curr['ema_50']) and (curr['volume'] > curr['avg_vol_20']):
            msg = f"🔴 <b>[TÍN HIỆU CÓ THỂ BÁN] THỦNG HỖ TRỢ TRUNG HẠN: {ticker}</b>\n" \
                  f"💰 Giá: {curr['close']:,} (Thủng EMA 50)\n⚠️ Volume xả: Lớn hơn trung bình 20 phiên!"

        # --- XỬ LÝ KẾT QUẢ TRẢ VỀ (Đã đổi sang HTML) ---
        if reply_chat_id and waiting_msg_id:
            if msg:
                bot.edit_message_text(msg, chat_id=reply_chat_id, message_id=waiting_msg_id, parse_mode='HTML')
            else:
                trend = "Tích cực (Trên EMA50)" if curr['close'] > curr['ema_50'] else "Tiêu cực (Dưới EMA50)"
                neutral_msg = f"⚪ <b>[ĐỨNG NGOÀI QUAN SÁT]: {ticker}</b>\n" \
                              f"Hiện tại chưa có tín hiệu có thể mua hay bán.\n\n" \
                              f"📝 <b>Thông số hiện tại:</b>\n" \
                              f"▪️ Giá đóng cửa: {curr['close']:,}\n" \
                              f"▪️ Xu hướng: {trend}\n" \
                              f"▪️ RSI(14): {curr['rsi_14']:.2f}"
                bot.edit_message_text(neutral_msg, chat_id=reply_chat_id, message_id=waiting_msg_id, parse_mode='HTML')
        else:
            if msg:
                bot.send_message(CHAT_ID, msg, parse_mode='HTML')
                print(f"👉 Đã tự động gửi tín hiệu cho {ticker}")

    except Exception as e:
        if reply_chat_id and waiting_msg_id:
            bot.edit_message_text(f"❌ Có lỗi bất ngờ khi phân tích mã <b>{ticker}</b>. Vui lòng thử lại.", 
                                  chat_id=reply_chat_id, message_id=waiting_msg_id, parse_mode='HTML')
        print(f"Lỗi {ticker}: {e}")

# ================= LỊCH TRÌNH TỰ ĐỘNG LÚC 15:00 =================
def auto_scan_job():
    print(f"\n--- [{datetime.datetime.now().strftime('%H:%M:%S')}] Bắt đầu quét thị trường tự động ---")
    for t in TICKERS:
        analyze_stock(t) # Gọi hàm không truyền chat_id để nó chạy chế độ tự động
    print("--- Hoàn tất ---")

def run_scheduler():
    days = [schedule.every().monday, schedule.every().tuesday, schedule.every().wednesday, 
            schedule.every().thursday, schedule.every().friday]
    for day in days:
        day.at("15:00").do(auto_scan_job)
        
    while True:
        schedule.run_pending()
        time.sleep(1)

# ================= XỬ LÝ TIN NHẮN TỪ NGƯỜI DÚNG =================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🤖 Chào mừng sếp! Sếp muốn soi mã nào thì cứ gõ thẳng tên mã (VD: HPG, FPT, SSI) vào đây nhé.")

@bot.message_handler(func=lambda message: True)
def handle_user_chat(message):
    ticker = message.text.strip().upper()
    
    if 2 <= len(ticker) <= 4 and ticker.isalpha():
        # Lấy được ID của tin nhắn chờ để truyền vào hàm phân tích
        waiting_msg = bot.reply_to(message, f"⏳ Đang phân tích mã {ticker} cho sếp...")
        analyze_stock(ticker, reply_chat_id=message.chat.id, waiting_msg_id=waiting_msg.message_id)
    else:
        bot.reply_to(message, "❌ Sếp vui lòng nhập đúng mã chứng khoán (VD: VCB, MWG).")

# ================= BẮT ĐẦU CHẠY HỆ THỐNG =================
if __name__ == "__main__":
    print("🚀 Khởi động Bot Telegram Trợ lý ảo...")
    
    thread = threading.Thread(target=run_scheduler)
    thread.daemon = True
    thread.start()
    
    print("Bot đang chờ sếp nhắn tin và đợi đến 15:00 mỗi ngày để quét tự động...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)