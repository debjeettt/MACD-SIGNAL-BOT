import ccxt
import pandas as pd
import ta
import pytz
import time
import threading
from datetime import datetime
from flask import Flask
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# =================== GMAIL SETUP ======================
SENDER_EMAIL = "debjeetsolmacd@gmail.com"
APP_PASSWORD = "czczkxwwsadeglzm"
RECEIVER_EMAIL = "debjeetbiswas01@gmail.com"

def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Gmail alert sent successfully.")
    except Exception as e:
        print("❌ Gmail failed:", str(e))


# ================== GLOBAL STATE ======================
exchange = ccxt.bybit()
used_indexes = set()
signals_in_phase = 0
last_macd_above = None
last_triggered_type = None


# =================== MACD FUNCTIONS ===================
def get_data():
    ohlcv = exchange.fetch_ohlcv('SOL/USDT:USDT', timeframe='15m', limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def add_macd(df):
    macd = ta.trend.MACD(close=df['close'], window_slow=35, window_fast=15, window_sign=13)
    df['macd'] = macd.macd()
    df['signal'] = macd.macd_signal()
    df['hist'] = macd.macd_diff()
    return df


# ================== SIGNAL CHECK LOGIC ===================
def check_macd_signals():
    global used_indexes, signals_in_phase, last_macd_above, last_triggered_type

    df = get_data()
    df = add_macd(df)

    for i in range(3, len(df) - 1):
        cur = df.iloc[i]
        prev1, prev2, prev3 = df.iloc[i - 1], df.iloc[i - 2], df.iloc[i - 3]
        next_candle = df.iloc[i + 1]

        # Skip if not the latest completed candle
        if next_candle['timestamp'] < df.iloc[-1]['timestamp']:
            continue

        ts = next_candle['timestamp'].tz_localize('UTC').tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %I:%M:%S %p')
        price = next_candle['open']
        hist = cur['hist']
        prev_hist = prev1['hist']
        signal = None
        trigger = None

        # === Track crossover phase ===
        macd_above = cur['macd'] > cur['signal']
        if last_macd_above is None:
            last_macd_above = macd_above
        elif macd_above != last_macd_above:
            signals_in_phase = 0
            last_macd_above = macd_above
            last_triggered_type = None

        if signals_in_phase >= 4:
            continue

        # === LONG signals ===
        if (
            i not in used_indexes and
            hist > 0 and hist > prev_hist and
            last_triggered_type != f"deep_green_{macd_above}"
        ):
            signal = "long"
            trigger = "Deep green MACD bar"
            used_indexes.add(i)
            last_triggered_type = f"deep_green_{macd_above}"

        elif all(idx not in used_indexes for idx in [i - 1, i - 2, i - 3]):
            h1, h2, h3 = prev1['hist'], prev2['hist'], prev3['hist']
            if h1 < 0 and h2 < 0 and h3 < 0 and h1 > h2 > h3:
                signal = "long"
                trigger = "3 rising red MACD bars"
                used_indexes.update([i - 1, i - 2, i - 3])
                last_triggered_type = None

        # === SHORT signals ===
        if (
            i not in used_indexes and
            hist < 0 and hist < prev_hist and
            last_triggered_type != f"deep_red_{macd_above}"
        ):
            signal = "short"
            trigger = "Deep red MACD bar"
            used_indexes.add(i)
            last_triggered_type = f"deep_red_{macd_above}"

        elif all(idx not in used_indexes for idx in [i - 1, i - 2, i - 3]):
            h1, h2, h3 = prev1['hist'], prev2['hist'], prev3['hist']
            if h1 > 0 and h2 > 0 and h3 > 0 and h1 < h2 < h3:
                signal = "short"
                trigger = "3 falling green MACD bars"
                used_indexes.update([i - 1, i - 2, i - 3])
                last_triggered_type = None

        if signal:
            emoji = "🟢" if signal == "long" else "🔴"
            asset = "SOL/USDT"
            print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"{emoji}  {signal.upper()} SIGNAL — {asset}")
            print(f"🕒 Time     : {ts}")
            print(f"💰 Price    : ${price:.2f}")
            print(f"🎯 Trigger  : {trigger}")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

            subject = f"{signal.upper()} SIGNAL - {asset}"
            body = f"""{emoji} {signal.upper()} SIGNAL TRIGGERED — {asset}

📅 Time      : {ts}
💰 Price     : ${price:.2f}
🎯 Triggered : {trigger}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Powered by MACD Signal Bot
👤 Made with ❤️ by Debjeet Biswas
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            send_email(subject, body)
            signals_in_phase += 1


# ================== UPTIME FLASK + LOOP ===================
@app.route('/')
def home():
    return "I'm alive!"

def run_bot_loop():
    while True:
        print("🔁 Bot running... checking for MACD signals.")
        try:
            check_macd_signals()
        except Exception as e:
            print("❌ Bot crashed:", e)
        time.sleep(90)

if __name__ == '__main__':
    threading.Thread(target=run_bot_loop).start()
    app.run(host='0.0.0.0', port=10000)
