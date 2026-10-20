import os
import sys
import time
import json
import random
import threading
import requests
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

sys.stdout.reconfigure(encoding='utf-8')

def get_bkk_now() -> datetime:
    """คืนค่าเวลาปัจจุบันของประเทศไทย (GMT+7) เสมอ แม้รันอยู่บน Cloud ต่างประเทศ"""
    return datetime.utcnow() + timedelta(hours=7)

# ================= Configuration =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8790446278:AAGsQeiivf-jSCrM87f7YyznahPwklfUF9U")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8713490893,-5092812499")
PORT = int(os.getenv("PORT", "10000"))

LAZADA_URL = "https://www.lazada.co.th/products/pre-order-iphone-duo-23-69-i16250067859-s127511251733.html"
SHOPEE_URL = "https://shopee.co.th/product/989284521/45567695488"
STATE_FILE = "state.json"

DEFAULT_LAZADA_COOKIE = "__wpkreporterwid_=3fd5db6f-9a66-4159-bf07-557398939278; hng=TH|th|THB|764; hng.sig=oIsIuLg2HAFiQqtULu6W5crlFW3isQ-99J1Gg1EhTPc; lwrid=AgGhL4Tq9BVzDCzWcypaX39uI5Gw; lzd_cid=5678560d-ebae-4e4a-b36a-c909b985a105; t_fv=1791798605019; t_uid=uw2gzXsJA19WcjbY7Kuu8r54IzRtT1Ch; cna=wZpTI3Pc/zwCAYbsFw4lJMwv; undefined_click_time=1792381249402; xlly_s=1; t_sid=WSP8mFf4IvOJec4oF1hTsS4ERByQEMf9; utm_channel=NA; _m_h5_tk=5992d56d9c35c3a23ba67643655b83ca_1792481119205; _m_h5_tk_enc=03858397b6764a7231b29551345f0b93; lwrtk=AAIEatdlRkbWWzFgIBwaN8n6c1Lku70NFE3eRh39aANLoO6W1tANT8Q=; epssw=14*B6_JJztDDW17Bo8PdzKoa0P-BznZPLcSoTg_5oHMoHUO-cDtbccmhyOBjz3lANCqkWDnD68oSDD9DDG4R9uNphMguOOnnvCzDSR11W9aS3n_4bcILV0BdtfPHBf07AC_yWkHhNBBaQkSjgSX8P-Ns8IQgDS4iT-XzG5TS4WsFM6owa0AciEeSS0GF4rDD6J4o6QDDrdfeXfZ8y0Gy0DDDDSUIx8Ze9iUBvPqbVSqBJicfEwXblpZDS3XMnympzfdMn5pSdrvPyi-M1LGJPFhOdfXzqBIjCSiA7LtRi8ZCOIV06EEhx0LgQfekIZ_It30wDDDrth_txiXcXcrPWjJ_rC2i_0kSRrN6RxIqXAHHcCxMZqaNW..; tfstk=feRjHHAhjoqjvjBYLF3rFS0BPgf1GnGE6P_9-FF4WsCYXlLd41u0Qxb11gtG0OIw_3T953Aa3mjNX3TM7KWAgO7_1FsWuGRNgdN14HeV0EBO2Q_CltLVHNUDEH8LgIkc_51cs1nEYXl_oEfG6T17ZESDyUbTX1NWeEYcszXyYegXoAwQJ_216hCRyNQf65BAD46R-wfTMOFYeuIlWURzXY2s9Fn7gSqJ421ppjaU8Q_-oMTfxabkNZ6fvtj76Od5lt1plBf-f6bJaQ6FUPuRwevyDa1IGkbXee1A5C0LCG66i__6Emw2Anb9yTtq7RbWCFdhi6atMU1fc9d62yFWvUT9LTOrJXffMipNiFzI0UOX0EAW7PeRGsJ5dI1d4hVFAYtuCz631asEP4wgI4gGzfhBoO61Habu84g7LRXArasEP4wgItQlrXuSPJyG."
LAZADA_COOKIE_RAW = os.getenv("LAZADA_COOKIE", DEFAULT_LAZADA_COOKIE)

def parse_cookies(cookie_raw: str) -> list:
    cookies = []
    for item in cookie_raw.split(";"):
        if "=" in item:
            name, val = item.strip().split("=", 1)
            cookies.append({
                "name": name,
                "value": val,
                "domain": ".lazada.co.th",
                "path": "/"
            })
    return cookies

# In-memory runtime metrics
RUNTIME_METRICS = {
    "status": "Active (Monitoring 24/7)",
    "start_time": get_bkk_now().strftime('%Y-%m-%d %H:%M:%S'),
    "total_checks": 0,
    "last_check_time": "-",
    "next_check_in_seconds": 0,
    "next_check_time": "-",
    "last_error": None,
    "last_delays": [],
    "recent_activity": []
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
    """ส่งข้อความเข้า Telegram (ส่งเฉพาะตอนของเข้า หรือของหมด)"""
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

def check_lazada(page, state: dict) -> tuple[bool, str]:
    """ตรวจเช็คสต็อก Lazada ทุกรุ่นย่อย พร้อมจับเวลาของเข้า-ของหมด"""
    state_changed = False
    now_bkk = get_bkk_now()
    now_ts = now_bkk.strftime('%H:%M:%S')
    print(f"\n🔍 [{now_ts}] ตรวจเช็ค Lazada...")
    status_summary = "ปกติ (สินค้าหมดทุกรุ่น)"
    try:
        page.goto(LAZADA_URL, wait_until="commit", timeout=25000)
        page.wait_for_timeout(3500)

        content = page.content()
        is_punish = ("punish" in page.url or 
                     "We need to check if you are a robot" in content or
                     page.locator("text='We need to check if you are a robot'").count() > 0)

        if is_punish:
            print("  ⚠️ [Lazada] พบบล็อก Captcha ชั่วคราว (จะข้ามรอบนี้ไปก่อน)")
            RUNTIME_METRICS["last_error"] = f"Lazada Captcha at {now_ts}"
            return state_changed, "ติด Captcha ชั่วคราว"

        colors = ["Star White", "Night Sky"]
        capacities = ["256GB", "512GB", "1TB", "2TB"]
        found_any = False
        in_stock_models = []

        for col in colors:
            col_el = page.locator(f"span.sku-variable-img-name:has-text('{col}'), div.sku-prop-content:has-text('{col}')")
            if col_el.count() > 0:
                found_any = True
                col_el.first.dispatch_event('click')
                page.wait_for_timeout(250)

            for cap in capacities:
                state_key = f"Lazada_{col}_{cap}"
                cap_el = page.locator(f"span.sku-variable-name-text:has-text('{cap}'), div.sku-prop-content:has-text('{cap}')")
                if cap_el.count() > 0:
                    found_any = True
                    cap_el.first.dispatch_event('click')
                    page.wait_for_timeout(200)

                is_out = (page.locator("text='สินค้าหมด'").count() > 0 or 
                          page.locator("text='สินค้าหมดสต็อก'").count() > 0)
                has_buy = page.locator("button:has-text('ซื้อเลย')").count() > 0
                has_cart = page.locator("button:has-text('เพิ่มลงในรถเข็น')").count() > 0

                is_available = (not is_out) and (has_buy or has_cart)
                prev_info = state.get(state_key, {})
                was_in_stock = prev_info.get("status") == "IN_STOCK"

                if is_available and not was_in_stock:
                    in_stock_models.append(f"{col} {cap}")
                    print(f"  🎉 [Lazada เข้าใหม่!] {col} {cap}")
                    msg = (
                        f"🚨🚨 <b>ของเข้าแล้วบน LAZADA!</b> 🚨🚨\n\n"
                        f"📱 <b>สินค้า:</b> iPhone Duo\n"
                        f"🎨 <b>สี:</b> {col}\n"
                        f"💾 <b>ความจุ:</b> {cap}\n"
                        f"⏰ <b>เวลาของเข้า:</b> {now_ts} น.\n\n"
                        f"👉 <a href='{LAZADA_URL}'>กดสั่งซื้อที่นี่ทันที</a>"
                    )
                    send_telegram(msg)
                    state[state_key] = {
                        "status": "IN_STOCK",
                        "in_stock_time": now_bkk.isoformat()
                    }
                    state_changed = True

                elif not is_available and was_in_stock:
                    start_iso = prev_info.get("in_stock_time")
                    start_dt = datetime.fromisoformat(start_iso) if start_iso else now_bkk
                    end_dt = now_bkk
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
            RUNTIME_METRICS["last_error"] = None
            if in_stock_models:
                status_summary = f"🎉 มีของเข้า: {', '.join(in_stock_models)}"
            else:
                status_summary = "ตรวจครบ 8 รุ่นย่อย (สินค้าหมด)"
        else:
            print("  ⚠️ Lazada โครงสร้างปุ่มตัวเลือกไม่พร้อม")
            status_summary = "โครงสร้างหน้าเว็บไม่ตอบสนอง"

    except Exception as e:
        print(f"  ❌ [Lazada Error] {e}")
        RUNTIME_METRICS["last_error"] = str(e)
        status_summary = f"Error: {e}"

    return state_changed, status_summary

def check_shopee(page, state: dict) -> tuple[bool, str]:
    """ตรวจเช็คสต็อก Shopee พร้อมจับเวลา"""
    state_changed = False
    now_bkk = get_bkk_now()
    now_ts = now_bkk.strftime('%H:%M:%S')
    print(f"🔍 [{now_ts}] ตรวจเช็ค Shopee...")
    status_summary = "ปกติ (สินค้าหมด)"
    try:
        page.goto(SHOPEE_URL, wait_until="commit", timeout=25000)
        page.wait_for_timeout(3000)

        thai_btn = page.locator("button:has-text('ไทย')")
        if thai_btn.count() > 0:
            thai_btn.first.click(force=True, timeout=2000)
            page.wait_for_timeout(1000)

        content = page.content()
        if "ต้องเข้าสู่ระบบ" in content:
            print("  ⚠️ [Shopee] หน้าร้านค้านี้ต้องใช้ล็อกอิน")
            return state_changed, "ต้องใช้ล็อกอิน"

        is_out = "สินค้าหมด" in content or "sold out" in content.lower()
        has_buy = page.locator("button:has-text('ซื้อสินค้า'), button:has-text('ซื้อเลย')").count() > 0
        is_available = (not is_out) and has_buy

        state_key = "Shopee_All"
        prev_info = state.get(state_key, {})
        was_in_stock = prev_info.get("status") == "IN_STOCK"

        if is_available and not was_in_stock:
            print("  🎉 [Shopee เข้าใหม่!]")
            msg = (
                f"🚨🚨 <b>ของเข้าแล้วบน SHOPEE!</b> 🚨🚨\n\n"
                f"📱 <b>สินค้า:</b> iPhone Duo\n"
                f"⏰ <b>เวลาของเข้า:</b> {now_ts} น.\n\n"
                f"👉 <a href='{SHOPEE_URL}'>กดสั่งซื้อที่ Shopee ทันที</a>"
            )
            send_telegram(msg)
            state[state_key] = {
                "status": "IN_STOCK",
                "in_stock_time": now_bkk.isoformat()
            }
            state_changed = True
            status_summary = "🎉 มีสินค้าพร้อมสั่งซื้อ!"

        elif not is_available and was_in_stock:
            start_iso = prev_info.get("in_stock_time")
            start_dt = datetime.fromisoformat(start_iso) if start_iso else now_bkk
            end_dt = now_bkk
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
            status_summary = "สินค้าเพิ่งหมดสต็อก"
        elif not is_available and state_key not in state:
            state[state_key] = {"status": "OUT_OF_STOCK"}
            status_summary = "ตรวจสอบแล้ว (ยังหมดอยู่)"
        else:
            print("  ✓ Shopee ตรวจสอบแล้ว (ยังหมดอยู่)")
            status_summary = "ตรวจสอบแล้ว (ยังหมดอยู่)"

    except Exception as e:
        print(f"  ❌ [Shopee Error] {e}")
        status_summary = f"Error: {e}"

    return state_changed, status_summary

def get_next_sleep_seconds() -> float:
    """สุ่มระยะเวลาพัก 50 - 90 วินาที แบบไม่เชิงเส้น (Non-linear distribution)"""
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

    state = load_state()
    if "total_checks" in state:
        RUNTIME_METRICS["total_checks"] = state["total_checks"]
    if "recent_activity" in state and isinstance(state["recent_activity"], list) and len(state["recent_activity"]) > 0:
        RUNTIME_METRICS["recent_activity"] = state["recent_activity"]
    RUNTIME_METRICS["status"] = "Active (Monitoring 24/7)"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--blink-settings=imagesEnabled=false",
                "--js-flags=--max-old-space-size=128"
            ]
        )
        def create_context_and_page(browser_inst):
            ctx = browser_inst.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="th-TH",
                viewport={"width": 1366, "height": 768}
            )
            cookies = parse_cookies(LAZADA_COOKIE_RAW)
            if cookies:
                ctx.add_cookies(cookies)
            pg = ctx.new_page()
            
            def block_heavy(route):
                try:
                    if route.request.resource_type in ["image", "media", "font"]:
                        route.abort()
                    else:
                        route.continue_()
                except Exception:
                    pass
            pg.route("**/*", block_heavy)

            Stealth().apply_stealth_sync(pg)
            return ctx, pg

        cycle_count = RUNTIME_METRICS.get("total_checks", 0)

        while True:
            cycle_count += 1
            RUNTIME_METRICS["total_checks"] = cycle_count
            now_bkk = get_bkk_now()
            check_time_str = now_bkk.strftime('%H:%M:%S')
            RUNTIME_METRICS["last_check_time"] = check_time_str

            print(f"\n==================== [ รอบที่ #{cycle_count} | {check_time_str} น. ] ====================")
            
            # บันทึกสถานะเริ่มรอบทันทีเพื่อให้ Dashboard แสดงผลเรียลไทม์เสมอ ไม่ต้องรอนาน
            current_log = {
                "cycle": cycle_count,
                "time": check_time_str,
                "lazada": "กำลังตรวจเช็ค...",
                "shopee": "รอตรวจ",
                "sleep": "-"
            }
            act_logs = RUNTIME_METRICS["recent_activity"]
            act_logs.append(current_log)
            RUNTIME_METRICS["recent_activity"] = act_logs[-15:]

            any_change = False
            context, page = None, None
            try:
                context, page = create_context_and_page(browser)

                c1, lzd_status = check_lazada(page, state)
                current_log["lazada"] = lzd_status
                current_log["shopee"] = "กำลังตรวจเช็ค..."
                
                time.sleep(random.uniform(1.0, 2.0))
                c2, shp_status = check_shopee(page, state)
                current_log["shopee"] = shp_status

                if c1 or c2:
                    any_change = True
            except Exception as e:
                print(f"[Loop Exception] {e}")
                RUNTIME_METRICS["last_error"] = str(e)
                current_log["lazada"] = f"Error: {e}"
            finally:
                if page:
                    try: page.close()
                    except: pass
                if context:
                    try: context.close()
                    except: pass

            # บันทึกสถานะ และประวัติรอบลง state.json ทุกครั้ง เพื่อให้ประวัติไม่หาย
            state["total_checks"] = cycle_count
            state["recent_activity"] = RUNTIME_METRICS["recent_activity"]
            save_state(state)

            # คำนวณช่วงเวลาสุ่ม 50 - 90 วินาที แบบ non-linear
            sleep_sec = get_next_sleep_seconds()
            next_run_dt = get_bkk_now() + timedelta(seconds=sleep_sec)
            RUNTIME_METRICS["next_check_in_seconds"] = sleep_sec
            RUNTIME_METRICS["next_check_time"] = next_run_dt.strftime('%H:%M:%S')
            current_log["sleep"] = f"{sleep_sec}s"
            
            delays = RUNTIME_METRICS["last_delays"]
            delays.append(sleep_sec)
            RUNTIME_METRICS["last_delays"] = delays[-10:]

            print(f"💤 สุ่มสลีปแบบ Non-linear: {sleep_sec} วินาที (ตรวจรอบถัดไปเวลา {RUNTIME_METRICS['next_check_time']} น.)...")
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

        # Check Activity rows (ประวัติการเช็คแบบเรียลไทม์)
        activity_rows = ""
        recent_act = RUNTIME_METRICS.get("recent_activity", [])
        for act in reversed(recent_act):
            activity_rows += (
                f"<tr>"
                f"<td><b>#{act.get('cycle')}</b></td>"
                f"<td>{act.get('time')} น.</td>"
                f"<td>{act.get('lazada')}</td>"
                f"<td>{act.get('shopee')}</td>"
                f"<td style='color:#38bdf8;'>พัก {act.get('sleep')}</td>"
                f"</tr>"
            )
        if not activity_rows:
            activity_rows = "<tr><td colspan='5' style='text-align:center; color:#94a3b8; padding:16px;'>กำลังเริ่มรอบการตรวจแรก...</td></tr>"

        # Restock History rows (ประวัติของเข้า)
        hist_rows = ""
        for h in reversed(history[-10:]):
            hist_rows += f"<tr><td>{h.get('platform')}</td><td>{h.get('model')}</td><td>{h.get('start_time')}</td><td>{h.get('duration')}</td></tr>"
        if not hist_rows:
            hist_rows = "<tr><td colspan='4' style='text-align:center; color:#94a3b8; padding:16px;'>ยังไม่มีประวัติสินค้าเข้า (บอทกำลังเฝ้ารอของเติมอย่างต่อเนื่อง 24 ชม.)</td></tr>"

        delays_preview = ", ".join([f"{d}s" for d in RUNTIME_METRICS["last_delays"][-6:]]) or "-"

        html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iPhone Duo Cloud Monitor - 24/7 Status</title>
    <meta http-equiv="refresh" content="20">
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
            max-width: 760px;
            width: 100%;
        }}
        .header {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .header h1 {{
            font-size: 24px;
            margin-bottom: 8px;
            color: #38bdf8;
        }}
        .badge-live {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(34, 197, 94, 0.2);
            color: #4ade80;
            padding: 6px 16px;
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
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
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
            font-size: 13px;
        }}
        th, td {{
            padding: 9px 10px;
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

        <!-- Live Activity Log -->
        <div class="section">
            <h2>📋 บันทึกประวัติการตรวจเช็คล่าสุด (Live Activity Logs)</h2>
            <table>
                <thead>
                    <tr><th>รอบที่</th><th>เวลา (ไทย)</th><th>Lazada (8 รุ่น)</th><th>Shopee</th><th>สุ่มพัก</th></tr>
                </thead>
                <tbody>
                    {activity_rows}
                </tbody>
            </table>
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
            <h2>🎉 ประวัติสินค้าเข้า (Restock Events)</h2>
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
        return

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthDashboardHandler)
    print(f"🌐 Threading HTTP Dashboard Server เริ่มทำงานที่ Port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    t_monitor = threading.Thread(target=monitor_loop, daemon=True)
    t_monitor.start()

    run_server()
