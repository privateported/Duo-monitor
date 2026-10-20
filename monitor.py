import os
import sys
import time
import json
import random
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

sys.stdout.reconfigure(encoding='utf-8')

# ================= ดึงข้อมูลจาก GitHub Secrets =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("[Error] ไม่พบ TELEGRAM_BOT_TOKEN หรือ TELEGRAM_CHAT_ID กรุณาตั้งค่าใน GitHub Secrets")
    sys.exit(1)

LAZADA_URL = "https://www.lazada.co.th/products/pre-order-iphone-duo-23-69-i16250067859-s127511251733.html"
SHOPEE_URL = "https://shopee.co.th/product/989284521/45567695488"
STATE_FILE = "state.json"

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
        
        if os.getenv("GITHUB_ACTIONS"):
            os.system('git config user.name "Stock Monitor Bot"')
            os.system('git config user.email "bot@github-actions.local"')
            os.system('git add state.json')
            os.system('git commit -m "Update stock state and restock history [skip ci]"')
            os.system('git push')
            print("✓ บันทึกประวัติและอัปเดต state.json ขึ้น GitHub สำเร็จ")
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
    """ส่งข้อความเข้า Telegram (รองรับทั้งแชทเดี่ยว, กลุ่ม, หรือหลายคนคั่นด้วยเครื่องหมายจุลภาค)"""
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
    print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] กำลังตรวจเช็ค Lazada...")
    try:
        page.goto(LAZADA_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)

        content = page.content()
        is_punish = ("punish" in page.url or 
                     "We need to check if you are a robot" in content or
                     page.locator("text='We need to check if you are a robot'").count() > 0)

        if is_punish:
            print("  ⚠️ [Lazada] ติดหน้าความปลอดภัย Captcha ของ Lazada")
            return state_changed

        colors = ["Star White", "Night Sky"]
        capacities = ["256GB", "512GB", "1TB", "2TB"]

        found_any = False

        for col in colors:
            col_el = page.locator(f"span:has-text('{col}')")
            if col_el.count() > 0:
                found_any = True
                col_el.first.click(force=True)
                page.wait_for_timeout(random.randint(300, 450))

            for cap in capacities:
                state_key = f"Lazada_{col}_{cap}"
                cap_el = page.locator(f"span:has-text('{cap}')")
                if cap_el.count() > 0:
                    found_any = True
                    cap_el.first.click(force=True)
                    page.wait_for_timeout(random.randint(300, 450))

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
                    
                    # บันทึกประวัติลง history list เพื่อแสดงบน Dashboard
                    if "history" not in state:
                        state["history"] = []
                    state["history"].append({
                        "platform": "Lazada",
                        "model": f"{col} {cap}",
                        "start_time": start_dt.strftime('%d/%m/%Y %H:%M:%S'),
                        "end_time": end_dt.strftime('%d/%m/%Y %H:%M:%S'),
                        "duration": duration_str
                    })
                    state["history"] = state["history"][-50:] # เก็บ 50 รายการล่าสุด
                    state_changed = True

        if found_any:
            print("  ✓ Lazada ตรวจสอบครบทุกรุ่น")
        else:
            print("  ⚠️ Lazada โครงสร้างหน้าเว็บไม่ตอบสนอง")

    except Exception as e:
        print(f"  ❌ [Lazada Error] {e}")

    return state_changed

def check_shopee(page, state: dict) -> bool:
    """ตรวจเช็คสต็อก Shopee พร้อมจับเวลา"""
    state_changed = False
    print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] กำลังตรวจเช็ค Shopee...")
    try:
        page.goto(SHOPEE_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)

        thai_btn = page.locator("button:has-text('ไทย')")
        if thai_btn.count() > 0:
            thai_btn.first.click()
            page.wait_for_timeout(2000)

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
        else:
            print("  ✓ Shopee ตรวจสอบแล้ว (ยังหมดอยู่)")

    except Exception as e:
        print(f"  ❌ [Shopee Error] {e}")

    return state_changed

def main():
    print("=" * 60)
    print("🚀 เริ่มรอบตรวจเช็คสต็อกบน GitHub Actions (รอบทุก 5 นาที)")
    print("=" * 60)

    jitter = round(random.uniform(1.0, 8.0), 2)
    print(f"🎲 Human Jitter Delay: พักสุ่มเวลา {jitter} วินาที ก่อนเริ่ม...")
    time.sleep(jitter)

    state = load_state()
    any_change = False

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="th-TH",
            viewport={"width": 1366, "height": 768}
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        c1 = check_lazada(page, state)
        time.sleep(random.uniform(2.0, 4.0))
        c2 = check_shopee(page, state)

        if c1 or c2:
            any_change = True

        browser.close()

    # บันทึกสถานะเริ่มต้นเสมอเพื่อให้ Dashboard มีข้อมูลแสดง
    if any_change or not os.path.exists(STATE_FILE):
        save_state(state)

    print("\n✓ เสร็จสิ้นรอบการทำงานเรียบร้อย!")

if __name__ == "__main__":
    main()
