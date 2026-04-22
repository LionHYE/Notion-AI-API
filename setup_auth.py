"""
One-time Notion login helper.
Run this once to save your Notion session to notion_auth.json.
After that, notion_ai.py runs fully headless — no browser window.

Usage:
    python setup_auth.py
"""
from playwright.sync_api import sync_playwright

AUTH_PATH = "notion_auth.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page    = context.new_page()

    page.goto("https://www.notion.so/login")
    print("請在瀏覽器中登入 Notion，完成後回到這裡按 Enter…")
    input()

    context.storage_state(path=AUTH_PATH)
    browser.close()

print(f"Session 已儲存至 {AUTH_PATH}，之後執行皆為 headless。")
