import ccxt
import pandas as pd
import ta
import pytz
from datetime import datetime

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail setup
SENDER_EMAIL = "debjeetsolmacd@gmail.com"         # Your new Gmail
APP_PASSWORD = "czczkxwwsadeglzm"        # Your 16-letter app password
RECEIVER_EMAIL = "debjeetbiswas01@gmail.com"       # Where alerts will go

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

# === 1. Get Data ===
exchange = ccxt.binance()
def get_data():
    ohlcv = exchange.fetch_ohlcv('SOLUSDT', timeframe='15m', limit=500)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# === 2. Add MACD ===
def add_macd(df):
    macd = ta.trend.MACD(close=df['close'], window_slow=35, window_fast=15, window_sign=13)
    df['macd'] = macd.macd()
    df['signal'] = macd.macd_signal()
    df['hist'] = macd.macd_diff()
    return df

# === 3. Setup ===
df = get_data()
df = add_macd(df)
used_indexes = set()
signals_in_phase = 0
last_macd_above = None
last_triggered_type = None

# === 4. Main Logic ===
for i in range(3, len(df) - 1):  # we access i+1 later
    cur = df.iloc[i]
    prev1, prev2, prev3 = df.iloc[i - 1], df.iloc[i - 2], df.iloc[i - 3]
    next_candle = df.iloc[i + 1]  # signal time is next candle's open

    # Convert to Indian time (next candle open)
    ts = next_candle['timestamp'].tz_localize('UTC').tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %I:%M:%S %p')
    price = next_candle['open']
    hist = cur['hist']
    prev_hist = prev1['hist']
    signal = None
    trigger = None

    # === 4.1 MACD Crossover Phase ===
    macd_above = cur['macd'] > cur['signal']
    if last_macd_above is None:
        last_macd_above = macd_above
    elif macd_above != last_macd_above:
        signals_in_phase = 0
        last_macd_above = macd_above
        last_triggered_type = None

    if signals_in_phase >= 3:
        continue  # too many signals in this phase

    # === 4.2 LONG SIGNALS ===

    # Deep green MACD bar
    if (
        i not in used_indexes and
        hist > 0 and hist > prev_hist and
        last_triggered_type != f"deep_green_{macd_above}"
    ):
        signal = "long"
        trigger = "Deep green MACD bar"
        used_indexes.add(i)
        last_triggered_type = f"deep_green_{macd_above}"

    # 3 increasing red MACD bars
    elif all(idx not in used_indexes for idx in [i - 1, i - 2, i - 3]):
        h1, h2, h3 = prev1['hist'], prev2['hist'], prev3['hist']
        if h1 < 0 and h2 < 0 and h3 < 0 and h1 > h2 > h3:
            signal = "long"
            trigger = "3 rising red MACD bars"
            used_indexes.update([i - 1, i - 2, i - 3])
            last_triggered_type = None  # allow deep bar after this

    # === 4.3 SHORT SIGNALS ===

    # Deep red MACD bar
    if (
        i not in used_indexes and
        hist < 0 and hist < prev_hist and
        last_triggered_type != f"deep_red_{macd_above}"
    ):
        signal = "short"
        trigger = "Deep red MACD bar"
        used_indexes.add(i)
        last_triggered_type = f"deep_red_{macd_above}"

    # 3 decreasing green MACD bars
    elif all(idx not in used_indexes for idx in [i - 1, i - 2, i - 3]):
        h1, h2, h3 = prev1['hist'], prev2['hist'], prev3['hist']
        if h1 > 0 and h2 > 0 and h3 > 0 and h1 < h2 < h3:
            signal = "short"
            trigger = "3 falling green MACD bars"
            used_indexes.update([i - 1, i - 2, i - 3])
            last_triggered_type = None  # reset deep trigger

    # === 4.4 OUTPUT ===
if signal:
    emoji = "🟢" if signal == "long" else "🔴"
    asset = "SOL/USDT"

    # Terminal Output
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"{emoji}  {signal.upper()} SIGNAL — {asset}")
    print(f"🕒 Time     : {ts}")
    print(f"💰 Price    : ${price:.2f}")
    print(f"🎯 Trigger  : {trigger}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # Gmail Output
    subject = f"{signal.upper()} SIGNAL - {asset}"
    body = f"""
{emoji} {signal.upper()} SIGNAL TRIGGERED — {asset}

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
