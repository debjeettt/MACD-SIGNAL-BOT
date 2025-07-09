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
        "used_signal_bars": [],
        "last_light_streak": None,
        "last_deep_type": None
    }

def get_data():
    ohlcv = exchange.fetch_ohlcv('INIT/USDT:USDT', timeframe='15m', limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def add_macd(df):
    macd = ta.trend.MACD(close=df['close'], window_slow=35, window_fast=15, window_sign=13)
    df['macd'] = macd.macd()
    df['signal'] = macd.macd_signal()
    df['hist'] = macd.macd_diff()
    return df

def format_signal_html(signal_type, trigger, ts, price, asset, signal_id, bar_type, streak_length):
    # Gmail gradient card design from your first code!
    gradient = "linear-gradient(90deg, #00ffa3 0%, #dc1fff 100%)" if signal_type == "long" else "linear-gradient(90deg, #fc5c7d 0%, #6a82fb 100%)"
    emoji = "🟢" if signal_type == "long" else "🔴"
    badge = "LONG" if signal_type == "long" else "SHORT"
    badge_color = "#00ffa3" if signal_type == "long" else "#fc5c7d"
    streak_info = bar_type.replace('_',' ').title()
    if streak_length is not None:
        streak_info += f" | Streak: {streak_length}"
    return f"""
    <html>
    <body style="background:#1c1c1c;font-family:sans-serif;color:white;">
    <div style="background:{gradient};padding:20px;border-radius:10px;">
    <h2>{emoji} {signal_type.upper()} SIGNAL — {badge}</h2>
    <p><b>Asset:</b> {asset}</p>
    <p><b>Time:</b> {ts}</p>
    <p><b>Price:</b> ${price:.4f}</p>
    <p><b>Trigger:</b> {trigger}</p>
    <p><b>Type:</b> {streak_info}</p>
    <p><b>Signal ID:</b> {signal_id}</p>
    </div>
    </body>
    </html>
    """

def get_bar_type(hist, prev_hist):
    if hist > 0 and hist > prev_hist:
        return "deep_green"
    elif hist < 0 and hist < prev_hist:
        return "deep_red"
    elif hist > 0 and hist < prev_hist:
        return "light_green"
    elif hist < 0 and hist > prev_hist:
        return "light_red"
    else:
        return "none"

def check_macd_signals():
    state = load_state()
    used_signal_bars = set(state.get("used_signal_bars", []))
    last_light_streak = state.get("last_light_streak", None)
    last_deep_type = state.get("last_deep_type", None)
    df = get_data()
    df = add_macd(df)
    asset = "INIT/USDT"

    # Only process the last fully closed bar
    i = len(df) - 2
    cur = df.iloc[i]
    prev = df.iloc[i - 1]
    cur_type = get_bar_type(cur['hist'], prev['hist'])

    # For time/price, use the open of the next bar after the closed one
    if i + 1 < len(df):
        next_candle = df.iloc[i + 1]
        ts = next_candle['timestamp'].tz_localize('UTC').tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %I:%M:%S %p')
        price = next_candle['open']
    else:
        ts = cur['timestamp'].tz_localize('UTC').tz_convert('Asia/Kolkata').strftime('%Y-%m-%d %I:%M:%S %p')
        price = cur['close']

    unique_id = f"{cur_type}_{cur['timestamp']}"

    # Deep bar logic: Only send if not already sent for this bar AND not already signaled for this deep streak
    if cur_type in ['deep_green', 'deep_red']:
        # Only send if the deep type just changed, or if it's the first deep after a non-deep bar
        if last_deep_type != cur_type:
            if unique_id not in used_signal_bars:
                signal_type = "long" if cur_type == "deep_green" else "short"
                trigger = "Deep green MACD bar" if cur_type == "deep_green" else "Deep red MACD bar"
                signal_id = f"{cur_type}-{cur['timestamp']}"
                html_body = format_signal_html(
                    signal_type=signal_type,
                    trigger=trigger,
                    ts=ts,
                    price=price,
                    asset=asset,
                    signal_id=signal_id,
                    bar_type=cur_type,
                    streak_length=None
                )
                body = f"""{'🟢' if signal_type == 'long' else '🔴'} {signal_type.upper()} SIGNAL TRIGGERED — {asset}

Type        : {cur_type.replace('_', ' ').title()}
📅 Time     : {ts}
💰 Price    : ${price:.4f}
🎯 Trigger  : {trigger}
Signal ID   : {signal_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Powered by MACD Signal Bot — by debjeettt
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                subject = f"{signal_type.upper()} SIGNAL - {asset}"
                send_email(subject, body, html_body)
                used_signal_bars.add(unique_id)
                state["used_signal_bars"] = list(used_signal_bars)
                state["last_deep_type"] = cur_type
                save_state(state)
                print(f"✅ Signal sent: {trigger} → {signal_type.upper()}")
            else:
                print("No new deep signal.")
        else:
            print("Ignoring repeated deep signal per streak.")

    # Light bar logic: check streak for last 3 bars, only signal at first streak per run
    elif cur_type in ['light_green', 'light_red']:
        # Check last 3 consecutive bars are the same type
        if i >= 2:
            prev1_type = get_bar_type(df.iloc[i-1]['hist'], df.iloc[i-2]['hist'])
            prev2_type = get_bar_type(df.iloc[i-2]['hist'], df.iloc[i-3]['hist'])
            if prev1_type == cur_type and prev2_type == cur_type:
                # Only signal if last streak type is not current
                if last_light_streak != cur_type:
                    streak_id = f"{cur_type}_{cur['timestamp']}"
                    if streak_id not in used_signal_bars:
                        signal_type = "short" if cur_type == "light_green" else "long"
                        trigger = "3 consecutive light green MACD bars" if cur_type == "light_green" else "3 consecutive light red MACD bars"
                        signal_id = f"{cur_type}-{cur['timestamp']}"
                        html_body = format_signal_html(
                            signal_type=signal_type,
                            trigger=trigger,
                            ts=ts,
                            price=price,
                            asset=asset,
                            signal_id=signal_id,
                            bar_type=cur_type,
                            streak_length=3
                        )
                        body = f"""{'🔴' if signal_type == 'short' else '🟢'} {signal_type.upper()} SIGNAL TRIGGERED — {asset}

Type        : {cur_type.replace('_', ' ').title()}
Streak      : 3
📅 Time     : {ts}
💰 Price    : ${price:.4f}
🎯 Trigger  : {trigger}
Signal ID   : {signal_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Powered by MACD Signal Bot — by debjeettt
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                        subject = f"{signal_type.upper()} SIGNAL - {asset}"
                        send_email(subject, body, html_body)
                        used_signal_bars.add(streak_id)
                        state["used_signal_bars"] = list(used_signal_bars)
                        state["last_light_streak"] = cur_type
                        save_state(state)
                        print(f"✅ Signal sent: {trigger} → {signal_type.upper()}")
                    else:
                        print("No new light signal.")
                else:
                    print("Ignoring repeated light signal per streak.")
            else:
                # Streak broken, reset last_light_streak
                if last_light_streak is not None:
                    state["last_light_streak"] = None
                    save_state(state)
                print("No valid light streak.")
        else:
            print("Not enough bars for light streak check.")
    else:
        # Reset streak memory if neither deep nor light
        if last_light_streak is not None or last_deep_type is not None:
            state["last_light_streak"] = None
            state["last_deep_type"] = None
            save_state(state)
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
