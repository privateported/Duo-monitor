import os
import sys
import time
import json
import random
import threading
import requests
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

sys.stdout.reconfigure(encoding='utf-8')

# ================= Configuration =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8790446278:AAGsQeiivf-jSCrM87f7YyznahPwklfUF9U")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8713490893,-5092812499")
PORT = int(os.getenv("PORT", "10000"))

LAZADA_URL = "https://www.lazada.co.th/products/pre-order-iphone-duo-23-69-i16250067859-s127511251733.html"
SHOPEE_URL = "https://shopee.co.th/product/989284521/45567695488"
STATE_FILE = "state.json"

# In-memory runtime metrics
RUNTIME_METRICS = {
    "status": "Starting up...",
    "start_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    "total_checks": 0,
    "last_check_time": "-",
    "next_check_in_seconds": 0,
    "next_check_time": "-",
    "last_error": None,
    "last_delays": []
}

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[State Load Error] {e}")
    return {"history": []}

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[State Save Error] {e}")

def format_duration(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins == 0:
        return f"{secs} วินาที"
    elif mins < 60:
        return f"{mins} นาที" if secs == 0 else f"{mins} นาที {secs} วินาที"
    else:
        hours = mins // 60
        rem_mins = mins % 60
        return f"{hours} ชั่วโมง {rem_mins} นาที"

def send_telegram(text: str):
    """ส่งข้อความเข้า Telegram (รองรับหลาย chat id คั่นด้วยเครื่องหมายจุลภาค)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chat_ids = [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()]
    success = True
    for cid in chat_ids:
        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            print(f"Telegram ({cid}) status: {r.status_code}")
            if r.status_code != 200:
                success = False
        except Exception as e:
            print(f"[Telegram Error for {cid}] {e}")
            success = False
    return success

def check_lazada(page, state: dict) -> bool:
    """ตรวจเช็คสต็อก Lazada ทุกรุ่นย่อย พร้อมจับเวลาของเข้า-ของหมด"""
    state_changed = False
    now_ts = datetime.now().strftime('%H:%M:%S')
    print(f"\n🔍 [{now_ts}] ตรวจเช็ค Lazada...")
    try:
        page.goto(LAZADA_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)

        content = page.content()
        is_punish = ("punish" in page.url or 
                     "We need to check if you are a robot" in content or
                     page.locator("text='We need to check if you are a robot'").count() > 0)

        if is_punish:
            print("  ⚠️ [Lazada] พบบล็อก Captcha ชั่วคราว (จะข้ามรอบนี้ไปก่อน)")
            RUNTIME_METRICS["last_error"] = f"Lazada Captcha at {now_ts}"
            return state_changed

        colors = ["Star White", "Night Sky"]
        capacities = ["256GB", "512GB", "1TB", "2TB"]
        found_any = False

        for col in colors:
            col_el = page.locator(f"span:has-text('{col}')")
            if col_el.count() > 0:
                found_any = True
                col_el.first.click(force=True)
                page.wait_for_timeout(random.randint(250, 400))

            for cap in capacities:
                state_key = f"Lazada_{col}_{cap}"
                cap_el = page.locator(f"span:has-text('{cap}')")
                if cap_el.count() > 0:
                    found_any = True
                    cap_el.first.click(force=True)
                    page.wait_for_timeout(random.randint(250, 400))

                is_out = (page.locator("text='สินค้าหมด'").count() > 0 or 
                          page.locator("text='สินค้าหมดสต็อก'").count() > 0)
                has_buy = page.locator("button:has-text('ซื้อเลย')").count() > 0
                has_cart = page.locator("button:has-text('เพิ่มลงในรถเข็น')").count() > 0

                is_available = (not is_out) and (has_buy or has_cart)
                prev_info = state.get(state_key, {})
                was_in_stock = prev_info.get("status") == "IN_STOCK"

                if is_available and not was_in_stock:
                    now_str = datetime.now().strftime('%H:%M:%S')
                    print(f"  🎉 [Lazada เข้าใหม่!] {col} {cap}")
                    msg = (
                        f"🚨🚨 <b>ของเข้าแล้วบน LAZADA!</b> 🚨🚨\n\n"
                        f"📱 <b>สินค้า:</b> iPhone Duo\n"
                        f"🎨 <b>สี:</b> {col}\n"
                        f"💾 <b>ความจุ:</b> {cap}\n"
                        f"⏰ <b>เวลาของเข้า:</b> {now_str} น.\n\n"
                        f"👉 <a href='{LAZADA_URL}'>กดสั่งซื้อที่นี่ทันที</a>"
                    )
                    send_telegram(msg)
                    state[state_key] = {
                        "status": "IN_STOCK",
                        "in_stock_time": datetime.now().isoformat()
                    }
                    state_changed = True

                elif not is_available and was_in_stock:
                    start_iso = prev_info.get("in_stock_time")
                    start_dt = datetime.fromisoformat(start_iso) if start_iso else datetime.now()
                    end_dt = datetime.now()
                    duration_sec = (end_dt - start_dt).total_seconds()
                    duration_str = format_duration(duration_sec)

                    print(f"  ⏳ [Lazada หมดแล้ว] {col} {cap} (อยู่ได้ {duration_str})")
                    msg = (
                        f"⏳ <b>สินค้าหมดแล้ว! (สรุปประวัติ)</b>\n\n"
                        f"📱 <b>สินค้า:</b> iPhone Duo (LAZADA)\n"
                        f"🎨 <b>รุ่น:</b> {col} ({cap})\n"
                        f"⏱️ <b>ระยะเวลาที่ของอยู่:</b> <b>{duration_str}</b>\n"
                        f"⏰ <b>ช่วงเวลา:</b> {start_dt.strftime('%H:%M')} – {end_dt.strftime('%H:%M')} น."
                    )
                    send_telegram(msg)
                    state[state_key] = {
                        "status": "OUT_OF_STOCK",
                        "last_out_time": end_dt.isoformat()
                    }
                    
                    if "history" not in state:
                        state["history"] = []
                    state["history"].append({
                        "platform": "Lazada",
                        "model": f"{col} {cap}",
                        "start_time": start_dt.strftime('%d/%m/%Y %H:%M:%S'),
                        "end_time": end_dt.strftime('%d/%m/%Y %H:%M:%S'),
                        "duration": duration_str
                    })
                    state["history"] = state["history"][-50:]
                    state_changed = True
                elif not is_available and state_key not in state:
                    state[state_key] = {"status": "OUT_OF_STOCK"}

        if found_any:
            print("  ✓ Lazada ตรวจสอบครบทั้ง 8 รุ่นย่อย")
        else:
            print("  ⚠️ Lazada โครงสร้างปุ่มตัวเลือกไม่พร้อม")

    except Exception as e:
        print(f"  ❌ [Lazada Error] {e}")
        RUNTIME_METRICS["last_error"] = str(e)

    return state_changed

def check_shopee(page, state: dict) -> bool:
    """ตรวจเช็คสต็อก Shopee พร้อมจับเวลา"""
    state_changed = False
    now_ts = datetime.now().strftime('%H:%M:%S')
    print(f"🔍 [{now_ts}] ตรวจเช็ค Shopee...")
    try:
        page.goto(SHOPEE_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)

        thai_btn = page.locator("button:has-text('ไทย')")
        if thai_btn.count() > 0:
            thai_btn.first.click()
            page.wait_for_timeout(1500)

        content = page.content()
        if "ต้องเข้าสู่ระบบ" in content:
            print("  ⚠️ [Shopee] หน้าร้านค้านี้ต้องใช้ล็อกอิน")
            return state_changed

        is_out = "สินค้าหมด" in content or "sold out" in content.lower()
        has_buy = page.locator("button:has-text('ซื้อสินค้า'), button:has-text('ซื้อเลย')").count() > 0
        is_available = (not is_out) and has_buy

        state_key = "Shopee_All"
        prev_info = state.get(state_key, {})
        was_in_stock = prev_info.get("status") == "IN_STOCK"

        if is_available and not was_in_stock:
            now_str = datetime.now().strftime('%H:%M:%S')
            print("  🎉 [Shopee เข้าใหม่!]")
            msg = (
                f"🚨🚨 <b>ของเข้าแล้วบน SHOPEE!</b> 🚨🚨\n\n"
                f"📱 <b>สินค้า:</b> iPhone Duo\n"
                f"⏰ <b>เวลาของเข้า:</b> {now_str} น.\n\n"
                f"👉 <a href='{SHOPEE_URL}'>กดสั่งซื้อที่ Shopee ทันที</a>"
            )
            send_telegram(msg)
            state[state_key] = {
                "status": "IN_STOCK",
                "in_stock_time": datetime.now().isoformat()
            }
            state_changed = True

        elif not is_available and was_in_stock:
            start_iso = prev_info.get("in_stock_time")
            start_dt = datetime.fromisoformat(start_iso) if start_iso else datetime.now()
            end_dt = datetime.now()
            duration_sec = (end_dt - start_dt).total_seconds()
            duration_str = format_duration(duration_sec)

            print(f"  ⏳ [Shopee หมดแล้ว] (อยู่ได้ {duration_str})")
            msg = (
                f"⏳ <b>สินค้าหมดแล้ว! (สรุปประวัติ)</b>\n\n"
                f"📱 <b>สินค้า:</b> iPhone Duo (SHOPEE)\n"
                f"⏱️ <b>ระยะเวลาที่ของอยู่:</b> <b>{duration_str}</b>\n"
                f"⏰ <b>ช่วงเวลา:</b> {start_dt.strftime('%H:%M')} – {end_dt.strftime('%H:%M')} น."
            )
            send_telegram(msg)
            state[state_key] = {
                "status": "OUT_OF_STOCK",
                "last_out_time": end_dt.isoformat()
            }
            if "history" not in state:
                state["history"] = []
            state["history"].append({
                "platform": "Shopee",
                "model": "iPhone Duo",
                "start_time": start_dt.strftime('%d/%m/%Y %H:%M:%S'),
                "end_time": end_dt.strftime('%d/%m/%Y %H:%M:%S'),
                "duration": duration_str
            })
            state["history"] = state["history"][-50:]
            state_changed = True
        elif not is_available and state_key not in state:
            state[state_key] = {"status": "OUT_OF_STOCK"}
        else:
            print("  ✓ Shopee ตรวจสอบแล้ว (ยังหมดอยู่)")

    except Exception as e:
        print(f"  ❌ [Shopee Error] {e}")
        RUNTIME_METRICS["last_error"] = str(e)

    return state_changed

def get_next_sleep_seconds() -> float:
    """สุ่มระยะเวลาพัก 50 - 90 วินาที แบบไม่เชิงเส้น (Non-linear distribution)"""
    # กระจายค่าแบบสลับสุ่มหลาย Step ป้องกันการตรวจจับ pattern
    intervals = [50, 52, 56, 61, 67, 72, 78, 83, 87, 90]
    base = random.choice(intervals)
    jitter = random.uniform(-1.5, 2.5)
    result = round(max(50.0, min(90.0, base + jitter)), 1)
    return result

def monitor_loop():
    """ลูปหลักทำงาน 24/7 บน Cloud"""
    print("=" * 65)
    print("🚀 สตาร์ทระบบตรวจเช็คสต็อก iPhone Duo แบบ Always-On 24/7 (Cloud Runner)")
    print("=" * 65)

    # ส่งสัญญาณแจ้งเตือนเริ่มทำงานเข้า Telegram
    startup_msg = (
        "🟢 <b>ระบบตรวจสต็อก 24 ชม. เปิดใช้งานบน Cloud สำเร็จ!</b>\n\n"
        "⚡ <b>โหมดความถี่:</b> สุ่มตรวจทุก <b>50 – 90 วินาที</b> (Non-linear)\n"
        "🎯 <b>เป้าหมาย:</b> Lazada (8 รุ่นย่อย) + Shopee\n"
        "👥 <b>ผู้รับแจ้งเตือน:</b> แชทส่วนตัว + กลุ่ม iPhone Duo\n\n"
        "<i>ระบบจะเฝ้าดูตลอด 24 ชั่วโมงโดยที่คุณไม่ต้องเปิดคอมทิ้งไว้</i>"
    )
    send_telegram(startup_msg)

    state = load_state()
    RUNTIME_METRICS["status"] = "Active (Monitoring 24/7)"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="th-TH",
            viewport={"width": 1366, "height": 768}
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        cycle_count = 0

        while True:
            cycle_count += 1
            RUNTIME_METRICS["total_checks"] = cycle_count
            now = datetime.now()
            RUNTIME_METRICS["last_check_time"] = now.strftime('%H:%M:%S')

            print(f"\n==================== [ รอบที่ #{cycle_count} | {now.strftime('%d/%m %H:%M:%S')} ] ====================")
            
            any_change = False
            try:
                c1 = check_lazada(page, state)
                time.sleep(random.uniform(1.5, 3.0))
                c2 = check_shopee(page, state)

                if c1 or c2:
                    any_change = True
            except Exception as e:
                print(f"[Loop Exception] {e}")
                RUNTIME_METRICS["last_error"] = str(e)

            if any_change or not os.path.exists(STATE_FILE):
                save_state(state)

            # ทุก 40 รอบ ให้รีโหลด context เคลียร์ memory cache
            if cycle_count % 40 == 0:
                print("🧹 [Memory Maintenance] รีเฟรช browser context เพื่อรักษาความเร็วและหน่วยความจำ...")
                page.close()
                context.close()
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    locale="th-TH",
                    viewport={"width": 1366, "height": 768}
                )
                page = context.new_page()
                Stealth().apply_stealth_sync(page)

            # คำนวณช่วงเวลาสุ่ม 50 - 90 วินาที แบบ non-linear
            sleep_sec = get_next_sleep_seconds()
            next_run_dt = datetime.now() + timedelta(seconds=sleep_sec)
            RUNTIME_METRICS["next_check_in_seconds"] = sleep_sec
            RUNTIME_METRICS["next_check_time"] = next_run_dt.strftime('%H:%M:%S')
            
            delays = RUNTIME_METRICS["last_delays"]
            delays.append(sleep_sec)
            RUNTIME_METRICS["last_delays"] = delays[-10:]

            print(f"💤 สุ่มสลีปแบบ Non-linear: {sleep_sec} วินาที (ตรวจรอบถัดไปเวลา {RUNTIME_METRICS['next_check_time']})...")
            time.sleep(sleep_sec)

# ================= HTTP Health & Dashboard Server =================
class HealthDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            state = load_state()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            payload = {
                "metrics": RUNTIME_METRICS,
                "state": state
            }
            self.wfile.write(json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'))
            return

        # Render Web Service Dashboard & Health Check
        state = load_state()
        history = state.get("history", [])

        # Create live status table
        table_rows = ""
        colors = ["Star White", "Night Sky"]
        capacities = ["256GB", "512GB", "1TB", "2TB"]
        for col in colors:
            for cap in capacities:
                key = f"Lazada_{col}_{cap}"
                st = state.get(key, {}).get("status", "OUT_OF_STOCK")
                badge = '<span class="badge in-stock">🟢 มีสินค้า</span>' if st == "IN_STOCK" else '<span class="badge out">⚪ หมด</span>'
                table_rows += f"<tr><td>Lazada</td><td>{col} - {cap}</td><td>{badge}</td></tr>"

        shopee_st = state.get("Shopee_All", {}).get("status", "OUT_OF_STOCK")
        shopee_badge = '<span class="badge in-stock">🟢 มีสินค้า</span>' if shopee_st == "IN_STOCK" else '<span class="badge out">⚪ หมด</span>'
        table_rows += f"<tr><td>Shopee</td><td>ทุกรุ่น (รวม)</td><td>{shopee_badge}</td></tr>"

        # History rows
        hist_rows = ""
        for h in reversed(history[-10:]):
            hist_rows += f"<tr><td>{h.get('platform')}</td><td>{h.get('model')}</td><td>{h.get('start_time')}</td><td>{h.get('duration')}</td></tr>"
        if not hist_rows:
            hist_rows = "<tr><td colspan='4' style='text-align:center; color:#888;'>ยังไม่มีประวัติการเติมของบันทึกไว้</td></tr>"

        delays_preview = ", ".join([f"{d}s" for d in RUNTIME_METRICS["last_delays"][-6:]]) or "-"

        html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iPhone Duo Cloud Monitor - 24/7 Status</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 24px 16px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            max-width: 720px;
            width: 100%;
        }}
        .header {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .header h1 {{
            font-size: 24px;
            margin-bottom: 6px;
            color: #38bdf8;
        }}
        .badge-live {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(34, 197, 94, 0.2);
            color: #4ade80;
            padding: 6px 14px;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 14px;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }}
        .pulse {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #22c55e;
            box-shadow: 0 0 8px #22c55e;
            animation: blink 1.5s infinite;
        }}
        @keyframes blink {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }}
        .card {{
            background: #1e293b;
            padding: 14px;
            border-radius: 12px;
            border: 1px solid #334155;
            text-align: center;
        }}
        .card .title {{
            font-size: 12px;
            color: #94a3b8;
            margin-bottom: 4px;
        }}
        .card .val {{
            font-size: 18px;
            font-weight: bold;
            color: #f1f5f9;
        }}
        .section {{
            background: #1e293b;
            border-radius: 14px;
            border: 1px solid #334155;
            padding: 16px;
            margin-bottom: 18px;
        }}
        .section h2 {{
            font-size: 16px;
            margin-top: 0;
            margin-bottom: 12px;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            padding: 8px 10px;
            text-align: left;
            border-bottom: 1px solid #334155;
        }}
        th {{
            color: #94a3b8;
            font-size: 12px;
            text-transform: uppercase;
        }}
        .badge {{
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge.in-stock {{
            background: #166534;
            color: #86efac;
        }}
        .badge.out {{
            background: #334155;
            color: #94a3b8;
        }}
        .footer {{
            text-align: center;
            font-size: 12px;
            color: #64748b;
            margin-top: 24px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ iPhone Duo 24/7 Cloud Monitor</h1>
            <div class="badge-live"><div class="pulse"></div> กำลังทำงาน 24 ชม. (Render Cloud)</div>
        </div>

        <div class="cards">
            <div class="card">
                <div class="title">รอบการตรวจทั้งหมด</div>
                <div class="val">#{RUNTIME_METRICS['total_checks']}</div>
            </div>
            <div class="card">
                <div class="title">ตรวจรอบล่าสุด</div>
                <div class="val">{RUNTIME_METRICS['last_check_time']} น.</div>
            </div>
            <div class="card">
                <div class="title">รอบถัดไปใน</div>
                <div class="val" style="color:#38bdf8;">{RUNTIME_METRICS['next_check_in_seconds']}s</div>
            </div>
            <div class="card">
                <div class="title">ตรวจรอบถัดไปเวลา</div>
                <div class="val">{RUNTIME_METRICS['next_check_time']} น.</div>
            </div>
        </div>

        <div class="section">
            <h2>📱 สถานะสต็อกสินค้าปัจจุบัน</h2>
            <table>
                <thead>
                    <tr><th>แพลตฟอร์ม</th><th>รุ่น / ความจุ</th><th>สถานะ</th></tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>📜 ประวัติการเติมของ 10 ครั้งล่าสุด</h2>
            <table>
                <thead>
                    <tr><th>แพลตฟอร์ม</th><th>รุ่น</th><th>เวลาของเข้า</th><th>คงอยู่เป็นเวลา</th></tr>
                </thead>
                <tbody>
                    {hist_rows}
                </tbody>
            </table>
        </div>

        <div class="section" style="font-size: 13px; color: #94a3b8;">
            <b>🎲 รูปแบบการสุ่มเวลา (Non-linear Delay Recent):</b> {delays_preview}
            <br>
            <i>หมายเหตุ: ระบบทำงานสุ่มพัก 50 - 90 วินาทีแบบไม่คงที่ เพื่อความปลอดภัยสูงสุดและไม่โดนแบน</i>
        </div>

        <div class="footer">
            iPhone Duo Auto Stock Bot • เชื่อมต่อ Telegram Bot & กลุ่มเรียบร้อยแล้ว
        </div>
    </div>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        # ปิด log ธรรมดาของ HTTP server ไม่ให้รก console
        return

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthDashboardHandler)
    print(f"🌐 HTTP Dashboard Server เริ่มทำงานที่ Port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    # รัน HTTP server ใน background thread เพื่อรองรับ Render health check & live dashboard
    t_server = threading.Thread(target=run_server, daemon=True)
    t_server.start()

    # รัน monitoring loop 24/7 ใน main thread
    monitor_loop()
