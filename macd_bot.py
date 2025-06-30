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
import json
import os

app = Flask(__name__)

# ========== GMAIL SETUP ==========
SENDER_EMAIL = "debjeetsolmacd@gmail.com"
APP_PASSWORD = "czczkxwwsadeglzm"
RECEIVER_EMAIL = "debjeetsolmacd01@gmail.com"

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

# ========== EXCHANGE SETUP ==========
exchange = ccxt.bybit()

# ========== PERSISTENT STATE ==========
STATE_FILE = "signal_state.json"

def save_state(used_indexes, last_signal_index, last_signal_type):
    state = {
        "used_indexes": list(used_indexes),
        "last_signal_index": last_signal_index,
        "last_signal_type": last_signal_type,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                return set(state["used_indexes"]), state["last_signal_index"], state["last_signal_type"]
        except Exception as e:
            print(f"Warning: could not load state file: {e}")
    return set(), None, None

# ========== GLOBAL STATE ==========
used_indexes, last_signal_index, last_signal_type = load_state()
signals_in_phase = 0
last_macd_sign = None

# ========== DATA FETCHING ==========
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

# ========== SIGNAL LOGIC ==========
def format_signal_html(signal, trigger, ts, price, asset):
    theme = {
        "long":   {"color": "#1ecb5c", "emoji": "🟢", "header": "LONG SIGNAL"},
        "short":  {"color": "#ff3b3b", "emoji": "🔴", "header": "SHORT SIGNAL"},
    }
    s = theme["long"] if signal == "long" else theme["short"]

    html = f"""
    <html>
    <body style="background: #f5f7fa; padding: 0; margin: 0; font-family: 'Segoe UI', Arial, sans-serif;">
      <table width="100%" style="background: #f5f7fa; padding: 0; margin: 0;">
        <tr>
          <td>
            <div style="max-width:440px;margin:40px auto;background:#fff;border-radius:18px;box-shadow:0 6px 32px #0002;padding:0;">
              <div style="border-radius:18px 18px 0 0;background:{s['color']}22;padding:22px 34px 8px;">
                <div style="font-size:36px;font-weight:700; color:{s['color']};letter-spacing:2px;line-height:1.2;">
                  {s['emoji']} {s['header']}
                </div>
                <div style="font-size:16px;color:#444;margin-top:2px;letter-spacing:1px;">
                  {asset}
                </div>
              </div>
              <div style="padding:22px 32px;">
                <table cellpadding="0" cellspacing="0" style="width:100%;font-size:16px;">
                  <tr>
                    <td style="padding-bottom:10px;"><b>Time</b>:</td>
                    <td style="padding-bottom:10px;text-align:right;color:#444;">{ts}</td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:10px;"><b>Price</b>:</td>
                    <td style="padding-bottom:10px;text-align:right;font-weight:600;color:#007bff;">${price:.2f}</td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:10px;"><b>Trigger</b>:</td>
                    <td style="padding-bottom:10px;text-align:right;color:{s['color']};font-weight:600;">{trigger}</td>
                  </tr>
                </table>
                <div style="margin-top:22px;text-align:center;">
                  <a href="https://www.tradingview.com/chart/?symbol=BYBIT:SOLUSDT" style="background:{s['color']};color:#fff;font-weight:700;text-decoration:none;padding:10px 30px;border-radius:8px;font-size:18px;box-shadow:0 2px 8px #0002;">View Chart</a>
                </div>
              </div>
              <div style="background:#f2f2f6;border-radius:0 0 18px 18px;padding:18px 32px 12px;">
                <div style="font-size:14px;color:#888;text-align:center;">
                🤖 <b>MACD Signal Bot</b> &bull; <span style="color:#e25555;">&#10084;&#65039;</span> by Debjeet Biswas<br>
                <span style="font-size:12px;">This is an automated signal. Please manage your risk.</span>
                </div>
              </div>
            </div>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """
    return html

def check_macd_signals():
    global used_indexes, signals_in_phase, last_macd_sign, last_signal_index, last_signal_type

    df = get_data()
    df = add_macd(df)

    for i in range(3, len(df)-1):
        cur = df.iloc[i]
        prev1, prev2, prev3 = df.iloc[i-1], df.iloc[i-2], df.iloc[i-3]
        next_candle = df.iloc[i+1]

        # Only send a signal at the most recent new candle open
        if next_candle['timestamp'] < df.iloc[-1]['timestamp']:
            continue

        ts = next_candle['timestamp'].tz_localize('UTC').tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %I:%M:%S %p')
        price = next_candle['open']
        hist = cur['hist']
        prev_hist = prev1['hist']
        macd_val = cur['macd']
        macd_signal_val = cur['signal']

        # Detect MACD crossover (color change)
        macd_sign = macd_val > macd_signal_val
        if last_macd_sign is None:
            last_macd_sign = macd_sign
        elif macd_sign != last_macd_sign:
            signals_in_phase = 0
            crossover_type = None
            signal = None
            trigger = None
            if macd_sign and not last_macd_sign:
                crossover_type = "bullish"
                signal = "long"
                trigger = "Bullish crossover"
            elif not macd_sign and last_macd_sign:
                crossover_type = "bearish"
                signal = "short"
                trigger = "Bearish crossover"
            if signal:
                emoji = "🟢" if signal == "long" else "🔴"
                asset = "SOL/USDT"
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
                html_body = format_signal_html(signal, trigger, ts, price, asset)
                send_email(subject, body, html_body)
                signals_in_phase += 1
                # Save state after sending a signal
                save_state(used_indexes, last_signal_index, last_signal_type)
            last_macd_sign = macd_sign
            last_signal_type = None
            last_signal_index = None

        if signals_in_phase >= 4:
            continue  # Safety: prevent spamming

        signal = None
        trigger = None

        # === Deep Green (Long) ===
        is_deep_green = hist > 0 and hist > prev_hist
        # === Deep Red (Short) ===
        is_deep_red = hist < 0 and hist < prev_hist
        # === Light Red (for 3-in-row) ===
        def is_light_red(idx):
            h = df.iloc[idx]['hist']
            prev_h = df.iloc[idx-1]['hist']
            return h < 0 and h > prev_h
        # === Light Green (for 3-in-row) ===
        def is_light_green(idx):
            h = df.iloc[idx]['hist']
            prev_h = df.iloc[idx-1]['hist']
            return h > 0 and h < prev_h

        # === LONG SIGNALS ===
        if (
            i not in used_indexes and
            is_deep_green and
            (last_signal_type != "long" or last_signal_index != i)
        ):
            signal = "long"
            trigger = "Deep green MACD bar"
            used_indexes.add(i)
            last_signal_type = "long"
            last_signal_index = i

        # 3 consecutive light red: only once per sequence
        elif (
            all(idx not in used_indexes for idx in [i-2, i-1, i]) and
            is_light_red(i) and is_light_red(i-1) and is_light_red(i-2)
        ):
            signal = "long"
            trigger = "3 consecutive light red MACD bars"
            used_indexes.update([i-2, i-1, i])
            last_signal_type = "long"
            last_signal_index = i

        # === SHORT SIGNALS ===
        if (
            i not in used_indexes and
            is_deep_red and
            (last_signal_type != "short" or last_signal_index != i)
        ):
            signal = "short"
            trigger = "Deep red MACD bar"
            used_indexes.add(i)
            last_signal_type = "short"
            last_signal_index = i

        # 3 consecutive light green: only once per sequence
        elif (
            all(idx not in used_indexes for idx in [i-2, i-1, i]) and
            is_light_green(i) and is_light_green(i-1) and is_light_green(i-2)
        ):
            signal = "short"
            trigger = "3 consecutive light green MACD bars"
            used_indexes.update([i-2, i-1, i])
            last_signal_type = "short"
            last_signal_index = i

        # Send signal
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
            html_body = format_signal_html(signal, trigger, ts, price, asset)
            send_email(subject, body, html_body)
            signals_in_phase += 1
            # Save state after sending a signal
            save_state(used_indexes, last_signal_index, last_signal_type)

# ========== KEEP BOT + FLASK ALIVE ==========
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
