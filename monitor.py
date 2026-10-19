import os
import sys
import time
import random
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

sys.stdout.reconfigure(encoding='utf-8')

# ================= Telegram Credentials =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8790446278:AAGsQeiivf-jSCrM87f7YyznahPwklfUF9U")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8713490893")

LAZADA_URL = "https://www.lazada.co.th/products/pre-order-iphone-duo-23-69-i16250067859-s127511251733.html"
SHOPEE_URL = "https://shopee.co.th/product/989284521/45567695488"

def send_telegram(text: str):
    """ส่งข้อความเข้า Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"Telegram status: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False

def check_lazada(page):
    """ตรวจเช็คสต็อก Lazada ทุกรุ่นย่อย"""
    print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] กำลังตรวจเช็ค Lazada...")
    try:
        page.goto(LAZADA_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)

        content = page.content()
        is_punish = ("punish" in page.url or 
                     "We need to check if you are a robot" in content or
                     page.locator("text='We need to check if you are a robot'").count() > 0)

        if is_punish:
            print("  ⚠️ [Lazada] ติดหน้าความปลอดภัย Captcha ของ Lazada บน GitHub Runner")
            return

        colors = ["Star White", "Night Sky"]
        capacities = ["256GB", "512GB", "1TB", "2TB"]

        found_any = False
        in_stock_items = []

        for col in colors:
            col_el = page.locator(f"span:has-text('{col}')")
            if col_el.count() > 0:
                found_any = True
                col_el.first.click(force=True)
                page.wait_for_timeout(400)

            for cap in capacities:
                cap_el = page.locator(f"span:has-text('{cap}')")
                if cap_el.count() > 0:
                    found_any = True
                    cap_el.first.click(force=True)
                    page.wait_for_timeout(400)

                is_out = (page.locator("text='สินค้าหมด'").count() > 0 or 
                          page.locator("text='สินค้าหมดสต็อก'").count() > 0)
                has_buy = page.locator("button:has-text('ซื้อเลย')").count() > 0
                has_cart = page.locator("button:has-text('เพิ่มลงในรถเข็น')").count() > 0

                if (not is_out) and (has_buy or has_cart):
                    print(f"  🎉 [Lazada In Stock!] {col} - {cap}")
                    in_stock_items.append(f"{col} ({cap})")

        if in_stock_items:
            items_str = ", ".join(in_stock_items)
            msg = (
                f"🚨🚨 <b>ของเข้าแล้วบน LAZADA!</b> 🚨🚨\n\n"
                f"📱 <b>สินค้า:</b> iPhone Duo\n"
                f"✨ <b>รุ่นที่มีของ:</b> {items_str}\n"
                f"⏰ <b>เวลา:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"👉 <a href='{LAZADA_URL}'>กดสั่งซื้อที่นี่ทันที</a>"
            )
            send_telegram(msg)
        elif found_any:
            print("  ✓ Lazada ตรวจสอบครบทุกรุ่น (ยังหมดอยู่)")
        else:
            print("  ⚠️ Lazada โครงสร้างหน้าเว็บไม่ตอบสนอง")

    except Exception as e:
        print(f"  ❌ [Lazada Error] {e}")

def check_shopee(page):
    """ตรวจเช็คสต็อก Shopee"""
    print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] กำลังตรวจเช็ค Shopee...")
    try:
        page.goto(SHOPEE_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)

        # ข้ามปุ่มเลือกภาษาถ้ามี
        thai_btn = page.locator("button:has-text('ไทย')")
        if thai_btn.count() > 0:
            thai_btn.first.click()
            page.wait_for_timeout(2000)

        content = page.content()
        if "ต้องเข้าสู่ระบบ" in content:
            print("  ⚠️ [Shopee] หน้าร้านค้านี้ต้องใช้ล็อกอิน")
            return

        is_out = "สินค้าหมด" in content or "sold out" in content.lower()
        has_buy = page.locator("button:has-text('ซื้อสินค้า'), button:has-text('ซื้อเลย')").count() > 0

        if not is_out and has_buy:
            print("  🎉 [Shopee In Stock!]")
            msg = (
                f"🚨🚨 <b>ของเข้าแล้วบน SHOPEE!</b> 🚨🚨\n\n"
                f"📱 <b>สินค้า:</b> iPhone Duo\n"
                f"⏰ <b>เวลา:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"👉 <a href='{SHOPEE_URL}'>กดสั่งซื้อที่ Shopee ทันที</a>"
            )
            send_telegram(msg)
        else:
            print("  ✓ Shopee ตรวจสอบแล้ว (ยังหมดอยู่)")

    except Exception as e:
        print(f"  ❌ [Shopee Error] {e}")

def main():
    print("=" * 60)
    print("🚀 เริ่มรอบตรวจเช็คสต็อกบน GitHub Actions")
    print("=" * 60)

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

        # ตรวจเช็ค 2 รอบใน 1 Workflow Run เพื่อความถี่สูงสุดและประหยัด Action minutes
        for cycle in range(1, 3):
            print(f"\n--- รอบที่ {cycle}/2 ---")
            check_lazada(page)
            time.sleep(5)
            check_shopee(page)

            if cycle < 2:
                # พัก 70 วินาทีก่อนเช็ครอบที่ 2 ใน Run เดียวกัน
                print("\n💤 พักรอ 70 วินาทีเพื่อเช็ครอบที่ 2...")
                time.sleep(70)

        browser.close()
    print("\n✓ เสร็จสิ้นรอบการทำงานบน GitHub Actions เรียบร้อย!")

if __name__ == "__main__":
    main()
