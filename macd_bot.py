import ccxt
import pandas as pd
import ta
import time
import threading
from datetime import datetime
from flask import Flask
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os

app = Flask(__name__)

# Gmail credentials
SENDER_EMAIL = "debjeetsolmacd@gmail.com"
APP_PASSWORD = "czczkxwwsadeglzm"
RECEIVER_EMAIL = "debjeetsolmacd01@gmail.com"

exchange = ccxt.bybit()

# Persistent state file
STATE_FILE = "signal_state_v2.json"

def send_email(subject, body, html_body=None):
    msg = MIMEMultipart("alternative")
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("✅ Gmail alert sent successfully.")
    except Exception as e:
        print("❌ Gmail failed:", str(e))

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: could not load state file: {e}")
    return {"used_signal_bars": []}

def get_data():
    ohlcv = exchange.fetch_ohlcv('MKR/USDT:USDT', timeframe='15m', limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def add_macd(df):
    macd = ta.trend.MACD(close=df['close'], window_slow=35, window_fast=15, window_sign=13)
    df['macd'] = macd.macd()
    df['signal'] = macd.macd_signal()
    df['hist'] = macd.macd_diff()
    return df

def format_signal_html(signal_type, trigger, ts, price, asset, signal_id):
    if signal_type == "long":
        gradient = "linear-gradient(90deg, #00ffa3 0%, #dc1fff 100%)"
        emoji = "🟢"
        badge = "LONG"
        badge_color = "#00ffa3"
    else:
        gradient = "linear-gradient(90deg, #fc5c7d 0%, #6a82fb 100%)"
        emoji = "🔴"
        badge = "SHORT"
        badge_color = "#fc5c7d"

    html = f"""
    <html>
    <body style="background:#1c1c1c;font-family:sans-serif;color:white;">
    <div style="background:{gradient};padding:20px;border-radius:10px;">
    <h2>{emoji} {signal_type.upper()} SIGNAL — {badge}</h2>
    <p><b>Asset:</b> {asset}</p>
    <p><b>Time:</b> {ts}</p>
    <p><b>Price:</b> ${price:.2f}</p>
    <p><b>Trigger:</b> {trigger}</p>
    <p><b>Signal ID:</b> {signal_id}</p>
    </div>
    </body>
    </html>
    """
    return html

def check_macd_signals():
    state = load_state()
    used_signal_bars = set(state.get("used_signal_bars", []))
    df = get_data()
    df = add_macd(df)
    asset = "MKR/USDT"

    for i in range(3, len(df) - 1):
        cur = df.iloc[i]
        prev1 = df.iloc[i-1]
        prev2 = df.iloc[i-2]
        prev3 = df.iloc[i-3]
        next_candle = df.iloc[i+1]
        unique_id = str(next_candle['timestamp'])

        if unique_id in used_signal_bars:
            continue

        ts = next_candle['timestamp'].tz_localize('UTC').tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %I:%M:%S %p')
        price = next_candle['open']
        signal_type = None
        trigger = None

        # === Deep green (long)
        if cur['hist'] > 0 and cur['hist'] > prev1['hist']:
            signal_type = "long"
            trigger = "Deep green MACD bar"

        # === Deep red (short)
        elif cur['hist'] < 0 and cur['hist'] < prev1['hist']:
            signal_type = "short"
            trigger = "Deep red MACD bar"

        # === 3 light red (long)
        elif (prev1['hist'] < 0 and prev2['hist'] < 0 and prev3['hist'] < 0 and
              prev1['hist'] > prev2['hist'] > prev3['hist'] and
              all(str(df.iloc[idx + 1]['timestamp']) not in used_signal_bars for idx in [i-1, i-2, i-3])):
            signal_type = "long"
            trigger = "3 consecutive light red MACD bars"

        # === 3 light green (short)
        elif (prev1['hist'] > 0 and prev2['hist'] > 0 and prev3['hist'] > 0 and
              prev1['hist'] < prev2['hist'] < prev3['hist'] and
              all(str(df.iloc[idx + 1]['timestamp']) not in used_signal_bars for idx in [i-1, i-2, i-3])):
            signal_type = "short"
            trigger = "3 consecutive light green MACD bars"

        if signal_type:
            signal_id = f"{signal_type}-{unique_id}"
            subject = f"{signal_type.upper()} SIGNAL - {asset}"
            body = f"""{'🟢' if signal_type == 'long' else '🔴'} {signal_type.upper()} SIGNAL TRIGGERED — {asset}

📅 Time      : {ts}
💰 Price     : ${price:.2f}
🎯 Triggered : {trigger}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Powered by MACD Signal Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            html_body = format_signal_html(signal_type, trigger, ts, price, asset, signal_id)
            send_email(subject, body, html_body)

            # Mark bars as used
            if "light" in trigger:
                for idx in [i-1, i-2, i-3]:
                    used_signal_bars.add(str(df.iloc[idx + 1]['timestamp']))
            else:
                used_signal_bars.add(unique_id)

            state["used_signal_bars"] = list(used_signal_bars)
            save_state(state)
            print(f"✅ Signal sent: {trigger} → {signal_type.upper()}")
            break

    else:
        print("No valid signal found.")

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
