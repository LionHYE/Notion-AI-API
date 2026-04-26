"""
Notion AI API — list_chats() 功能測試腳本
執行: python test_list_chats.py
"""
from __future__ import annotations

import traceback
import time
from datetime import datetime
from pathlib import Path

from notion_ai import NotionAI

def run_test():
    print("\n=== Notion AI API list_chats() 功能測試 ===\n")
    print(f"開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    ai = None
    try:
        # 初始化 NotionAI 並啟動
        ai = NotionAI(headless=False, debug=True)
        ai.start()
        url = ai._page.url
        if "/login" in url or "/sign-up" in url:
            print(f"❌ session 驗證失敗: 頁面 URL 含登入路徑: {url}")
            return
        else:
            print(f"✅ 啟動成功，URL: {url}")

        # 測試 list_chats()
        print("\n── 測試 list_chats() ──")
        try:
            t0 = time.time()
            chats = ai.list_chats()
            elapsed = time.time() - t0
            if chats:
                has_url = "url" in chats[0] if chats else False
                print(f"✅ list_chats() 首次: 返回 {len(chats)} 個項目，耗時 {elapsed:.1f}s，含 URL: {has_url}")
                print(f"   前三項: {chats[:3]}")
                
                if not has_url:
                    print(f"❌ list_chats() 缺 url 欄位: 返回值無 url 欄位（P5），無法與 chat()/get_messages() 串接")
            else:
                print(f"❌ list_chats() 首次: 返回空列表，耗時 {elapsed:.1f}s（P11/P12：selector 或面板問題）")
        except Exception as e:
            print(f"⚠️ list_chats() 首次: {e}")
            traceback.print_exc()

        # 連續第二次（驗證 P3 toggle bug）
        try:
            t0 = time.time()
            chats2 = ai.list_chats()
            elapsed = time.time() - t0
            if chats2:
                print(f"✅ list_chats() 連續第二次: 返回 {len(chats2)} 個項目，耗時 {elapsed:.1f}s")
            else:
                print(f"❌ list_chats() 連續第二次: 返回空列表，耗時 {elapsed:.1f}s（P3：toggle 非冪等，面板被關閉）")
        except Exception as e:
            print(f"⚠️ list_chats() 連續第二次: {e}（P3 可能導致 timeout）")
            traceback.print_exc()

        # 檢查 list_chats() 返回的詳細結構
        if chats:
            print("\n── list_chats() 返回結構分析 ──")
            # 分析第一個聊天項目的所有鍵
            first_chat = chats[0]
            print(f"第一個聊天項目的所有鍵: {list(first_chat.keys())}")
            
            # 檢查是否有 URL 相關欄位
            url_related_keys = [k for k in first_chat.keys() if 'url' in k.lower() or 'href' in k.lower() or 'link' in k.lower()]
            if url_related_keys:
                print(f"✅ 發現可能的 URL 相關欄位: {url_related_keys}")
                for key in url_related_keys:
                    print(f"   {key}: {first_chat[key]}")
            else:
                print("❌ 未發現任何 URL 相關欄位")
            
            # 檢查 react_id 欄位是否可用於構建 URL
            if 'react_id' in first_chat:
                print(f"react_id: {first_chat['react_id']} (可能可用於構建 URL)")
            
            # 檢查標題和時間
            if 'title' in first_chat:
                print(f"標題: {first_chat['title']}")
            if 'time' in first_chat:
                print(f"時間: {first_chat['time']}")

    except FileNotFoundError as e:
        print(f"⚠️ 找不到 auth 檔: {e}")
    except PermissionError as e:
        print(f"⚠️ Session 過期: {e}")
    except Exception as e:
        print(f"⚠️ 發生錯誤: {e}")
        traceback.print_exc()
    finally:
        # 關閉瀏覽器
        if ai:
            try:
                ai.close()
                print("\n✅ 瀏覽器已關閉")
            except Exception as e:
                print(f"⚠️ 關閉瀏覽器時發生錯誤: {e}")

if __name__ == "__main__":
    run_test()