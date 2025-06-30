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

SENDER_EMAIL = "debjeetsolmacd@gmail.com"
APP_PASSWORD = "czczkxwwsadeglzm"
RECEIVER_EMAIL = "debjeetsolmacd01@gmail.com"

exchange = ccxt.bybit()

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
    return {
        "used_signal_bars": []
    }

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
        header = "🚀 FUTURE LONG SIGNAL"
        emoji = "🟢"
        accent = "#00ffa3"
        futuristic_icon = "https://em-content.zobj.net/source/animated-noto-color-emoji/356/rocket_1f680.gif"
        badge = "LONG"
        badge_color = "#00ffa3"
    else:
        gradient = "linear-gradient(90deg, #fc5c7d 0%, #6a82fb 100%)"
        header = "⚡ FUTURE SHORT SIGNAL"
        emoji = "🔴"
        accent = "#fc5c7d"
        futuristic_icon = "https://em-content.zobj.net/source/animated-noto-color-emoji/356/high-voltage_26a1.gif"
        badge = "SHORT"
        badge_color = "#fc5c7d"

    html = f"""
    <html>
    <body style="background: #16181a; padding: 0; margin: 0; font-family: 'Segoe UI', Arial, sans-serif;">
      <div style="max-width:530px;margin:48px auto 10px auto;border-radius:24px;box-shadow:0 8px 44px #000b;padding:0;overflow:hidden;background: #23272f;">
        <div style="background: {gradient};padding:30px 40px 14px;position:relative;">
          <img src="{futuristic_icon}" width="68" style="position:absolute;top:18px;right:36px;filter:drop-shadow(0 6px 16px #0008);" />
          <div style="font-size:41px;font-weight:900;letter-spacing:1.1px;line-height:1.07;color:#fff;text-shadow:0 3px 20px #0009;">
            {emoji} {header}
          </div>
          <span style="display:inline-block; margin-top:15px; background:{badge_color}ee;color:#fff;font-size:22px;font-weight:800;padding:8px 32px 8px 28px;border-radius:22px;text-shadow:0 2px 12px #0007;letter-spacing:2.2px;box-shadow:0 3px 12px #0004;">
            {badge}
          </span>
        </div>
        <div style="padding:32px 40px 24px;">
          <table cellpadding="0" cellspacing="0" style="width:100%;font-size:20px;">
            <tr>
              <td><b>Asset</b>:</td>
              <td style="text-align:right;color:#fff;font-weight:700;">{asset}</td>
            </tr>
            <tr>
              <td><b>Time</b>:</td>
              <td style="text-align:right;color:#aaa;">{ts}</td>
            </tr>
            <tr>
              <td><b>Price</b>:</td>
              <td style="text-align:right;font-weight:800;color:{accent};">${price:.2f}</td>
            </tr>
            <tr>
              <td><b>Trigger</b>:</td>
              <td style="text-align:right;color:{accent};font-weight:700;">{trigger}</td>
            </tr>
            <tr>
              <td><b>Signal ID</b>:</td>
              <td style="text-align:right;font-size:14px;color:#888;">{signal_id}</td>
            </tr>
          </table>
          <div style="margin-top:34px;text-align:center;">
            <a href="https://www.tradingview.com/chart/?symbol=BYBIT:MKRUSDT" style="background:{accent};color:#191a1b;font-weight:900;text-decoration:none;padding:15px 38px;border-radius:12px;font-size:22px;box-shadow:0 3px 16px #0005;letter-spacing:1.3px;">🌐 View Live Chart</a>
          </div>
        </div>
        <div style="background:#1a1e22;border-radius:0 0 24px 24px;padding:20px 40px 18px;">
          <div style="font-size:15px;color:#aaa;text-align:center;">
            🤖 <b>MACD AI Signal Bot</b> &bull; <span style="color:#00ffa3;">#FUTURE</span> <span style="color:#fc5c7d;">#ALERT</span><br>
            <span style="font-size:13px;color:#666;">Automated signal. Not financial advice. <b>Trade smart. Ride the future.</b></span>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
    return html

def check_macd_signals():
    state = load_state()
    # Always use a set for fast lookup
    used_signal_bars = set(state.get("used_signal_bars", []))
    df = get_data()
    df = add_macd(df)
    asset = "MKR/USDT"

    # Only check last 3 confirmed candles (use i for the completed bar, next_candle for the next bar)
    for i in range(len(df)-4, len(df)-1):
        cur = df.iloc[i]
        prev1 = df.iloc[i-1]
        prev2 = df.iloc[i-2]
        next_candle = df.iloc[i+1]
        unique_id = str(next_candle['timestamp'])

        # SKIP if this bar was already used for a signal
        if unique_id in used_signal_bars:
            continue

        ts = next_candle['timestamp'].tz_localize('UTC').tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %I:%M:%S %p')
        price = next_candle['open']
        hist = cur['hist']
        prev_hist = prev1['hist']

        # --- Deep green (long) ---
        if hist > 0 and hist > prev_hist:
            signal_type = "long"
            signal_id = f"deepgreen-{unique_id}"
            trigger = "Deep green MACD bar"
        # --- Deep red (short) ---
        elif hist < 0 and hist < prev_hist:
            signal_type = "short"
            signal_id = f"deepred-{unique_id}"
            trigger = "Deep red MACD bar"
        # --- 3 consecutive light red (long) ---
        elif all(df.iloc[idx]['hist'] < 0 and df.iloc[idx]['hist'] > df.iloc[idx-1]['hist'] for idx in [i, i-1, i-2]):
            signal_type = "long"
            signal_id = f"3lightred-{unique_id}"
            trigger = "3 consecutive light red MACD bars"
        # --- 3 consecutive light green (short) ---
        elif all(df.iloc[idx]['hist'] > 0 and df.iloc[idx]['hist'] < df.iloc[idx-1]['hist'] for idx in [i, i-1, i-2]):
            signal_type = "short"
            signal_id = f"3lightgreen-{unique_id}"
            trigger = "3 consecutive light green MACD bars"
        else:
            continue  # No signal

        # If we reach here, a signal should be sent.
        subject = f"{signal_type.upper()} SIGNAL - {asset}"
        body = (
            (f"🟢" if signal_type == "long" else "🔴") +
            f" {signal_type.upper()} SIGNAL TRIGGERED — {asset}\n\n" +
            f"📅 Time      : {ts}\n" +
            f"💰 Price     : ${price:.2f}\n" +
            f"🎯 Triggered : {trigger}\n\n" +
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🤖 Powered by MACD Signal Bot\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        html_body = format_signal_html(signal_type, trigger, ts, price, asset, signal_id)
        send_email(subject, body, html_body)

        # Mark this bar as used
        used_signal_bars.add(unique_id)
        state["used_signal_bars"] = list(used_signal_bars)
        save_state(state)
        print(f"Signal sent and bar {unique_id} marked as used.")
        break  # Only send one signal per run

    else:
        print("No qualifying signals found (or already sent for these bars).")

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
