"""
Notion AI API — 完整功能測試腳本
執行: python test_all.py
輸出: test_report.md
"""
from __future__ import annotations

import traceback
import time
from datetime import datetime
from pathlib import Path

from notion_ai import NotionAI

REPORT_PATH = Path("test_report.md")

results: list[dict] = []


def record(tc: str, name: str, status: str, detail: str = "", output: str = "") -> None:
    results.append({"tc": tc, "name": name, "status": status, "detail": detail, "output": output})
    icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}.get(status, "?")
    print(f"  {icon} [{tc}] {name}: {status}")
    if detail:
        print(f"       {detail}")
    if output:
        preview = output[:200].replace("\n", " ").strip()
        print(f"       output: {preview}{'…' if len(output) > 200 else ''}")


def run_tests():
    print("\n=== Notion AI API 功能測試 ===\n")
    print(f"開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ──────────────────────────────────────────────────────
    # TC-01: start() / session 驗證
    # ──────────────────────────────────────────────────────
    print("── TC-01: start() / session 驗證 ──")
    ai = None
    try:
        ai = NotionAI(headless=False, debug=True)
        ai.start()
        url = ai._page.url
        if "/login" in url or "/sign-up" in url:
            record("TC-01", "session 驗證", "FAIL",
                   f"頁面 URL 含登入路徑: {url}")
        else:
            record("TC-01", "session 驗證", "PASS",
                   f"啟動成功，URL: {url}")
    except FileNotFoundError as e:
        record("TC-01", "session 驗證", "ERROR", f"找不到 auth 檔: {e}")
        return
    except PermissionError as e:
        record("TC-01", "session 驗證", "ERROR", f"Session 過期: {e}")
        return
    except Exception as e:
        record("TC-01", "session 驗證", "ERROR", f"{e}\n{traceback.format_exc()}")
        if ai:
            try:
                ai.close()
            except Exception:
                pass
        return

    try:
        # ──────────────────────────────────────────────────────
        # TC-03: get_models() 在 start() 後立即呼叫（尚在根目錄）
        # ──────────────────────────────────────────────────────
        print("\n── TC-03: get_models()（start() 後立即，尚在根目錄）──")
        t0 = time.time()
        try:
            models = ai.get_models()
            elapsed = time.time() - t0
            if models:
                record("TC-03a", "get_models()（根目錄）", "PASS",
                       f"返回 {len(models)} 個模型，耗時 {elapsed:.1f}s", str(models))
            else:
                record("TC-03a", "get_models()（根目錄）", "FAIL",
                       f"返回空列表，耗時 {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - t0
            record("TC-03a", "get_models()（根目錄）", "ERROR",
                   f"{e}，耗時 {elapsed:.1f}s")

        # ──────────────────────────────────────────────────────
        # TC-04 / TC-05 / TC-06b / TC-07：全部在同一個新聊天室裡完成
        # 整個測試過程只建立這一個聊天室
        # ──────────────────────────────────────────────────────

        # TC-04a: 建立新聊天室 + 基本串流回覆（唯一一次 _create_new_conversation）
        print("\n── TC-04: chat() 基本單輪 ──")
        try:
            t0 = time.time()
            chunks = []
            for chunk in ai.chat(prompt="用一句話打個招呼。", timeout=60):
                chunks.append(chunk)
                print(chunk, end="", flush=True)
            print()
            reply = "".join(chunks)
            elapsed = time.time() - t0
            current_url = ai._current_url
            if reply and reply.strip():
                record("TC-04a", "chat() 基本回覆", "PASS",
                       f"耗時 {elapsed:.1f}s，chunks={len(chunks)}，URL: {current_url}", reply)
            else:
                record("TC-04a", "chat() 基本回覆", "FAIL",
                       f"回覆為空，耗時 {elapsed:.1f}s")
        except TimeoutError as e:
            record("TC-04a", "chat() 基本回覆", "FAIL", str(e))
        except Exception as e:
            record("TC-04a", "chat() 基本回覆", "ERROR",
                   f"{e}\n{traceback.format_exc()}")

        # TC-04b: 特殊字元（繼續同一聊天室）
        try:
            t0 = time.time()
            reply2 = "".join(ai.chat(prompt="請輸出：Hello 世界 🌏", timeout=30))
            elapsed = time.time() - t0
            if reply2 and reply2.strip():
                record("TC-04b", "chat() 特殊字元", "PASS",
                       f"耗時 {elapsed:.1f}s", reply2[:100])
            else:
                record("TC-04b", "chat() 特殊字元", "FAIL",
                       f"回覆為空，耗時 {elapsed:.1f}s")
        except Exception as e:
            record("TC-04b", "chat() 特殊字元", "ERROR", str(e))

        # ──────────────────────────────────────────────────────
        # TC-05: 多輪對話（繼續同一聊天室）
        # ──────────────────────────────────────────────────────
        print("\n── TC-05: chat() 多輪對話 ──")
        r1 = r2 = r3 = None
        try:
            r1 = "".join(ai.chat(prompt="請記住數字 42，回覆「已記住」", timeout=30))
            record("TC-05a", "多輪第 1 輪", "PASS" if r1 and r1.strip() else "FAIL",
                   f"URL: {ai._current_url}", r1 or "")
        except Exception as e:
            record("TC-05a", "多輪第 1 輪", "ERROR", str(e))

        try:
            r2 = "".join(ai.chat(prompt="我剛才請你記住什麼數字？", timeout=30))
            if r2 and "42" in r2:
                record("TC-05b", "多輪第 2 輪（記憶）", "PASS", "", r2)
            elif r2:
                record("TC-05b", "多輪第 2 輪（記憶）", "FAIL",
                       f"回覆未含 42", r2)
            else:
                record("TC-05b", "多輪第 2 輪（記憶）", "FAIL", "回覆為空")
        except Exception as e:
            record("TC-05b", "多輪第 2 輪（記憶）", "ERROR", str(e))

        try:
            r3 = "".join(ai.chat(prompt="把這個數字乘以 2", timeout=30))
            if r3 and "84" in r3:
                record("TC-05c", "多輪第 3 輪（計算）", "PASS", "", r3)
            elif r3:
                record("TC-05c", "多輪第 3 輪（計算）", "FAIL", f"回覆未含 84", r3)
            else:
                record("TC-05c", "多輪第 3 輪（計算）", "FAIL", "回覆為空")
        except Exception as e:
            record("TC-05c", "多輪第 3 輪（計算）", "ERROR", str(e))

        # ──────────────────────────────────────────────────────
        # TC-02: list_chats()
        # ──────────────────────────────────────────────────────
        print("\n── TC-02: list_chats() ──")
        try:
            t0 = time.time()
            chats = ai.list_chats()
            elapsed = time.time() - t0
            if chats:
                has_url = "url" in chats[0]
                record("TC-02a", "list_chats() 首次", "PASS",
                       f"返回 {len(chats)} 個項目，耗時 {elapsed:.1f}s，含 URL: {has_url}",
                       str(chats[:3]))
                if not has_url:
                    record("TC-02a-P5", "list_chats() 缺 url 欄位", "FAIL",
                           "返回值無 url 欄位（P5）")
            else:
                record("TC-02a", "list_chats() 首次", "FAIL",
                       f"返回空列表，耗時 {elapsed:.1f}s")
        except Exception as e:
            record("TC-02a", "list_chats() 首次", "ERROR", str(e))

        # 連續第二次（驗證冪等）
        try:
            t0 = time.time()
            chats2 = ai.list_chats()
            elapsed = time.time() - t0
            if chats2:
                record("TC-02b", "list_chats() 連續第二次", "PASS",
                       f"返回 {len(chats2)} 個項目，耗時 {elapsed:.1f}s")
            else:
                record("TC-02b", "list_chats() 連續第二次", "FAIL",
                       f"返回空列表，耗時 {elapsed:.1f}s")
        except Exception as e:
            record("TC-02b", "list_chats() 連續第二次", "ERROR", str(e))

        # ──────────────────────────────────────────────────────
        # TC-06a: chat() 指定錯誤 model → 應拋 ValueError（在原聊天室送出前攔截，不送訊息）
        # ──────────────────────────────────────────────────────
        print("\n── TC-06: chat() 指定錯誤 model ──")
        try:
            "".join(ai.chat(prompt="測試", model="完全不存在的模型XYZ", timeout=30))
            record("TC-06a", "chat() 錯誤 model 靜默失敗", "FAIL",
                   "預期拋出 ValueError 但靜默繼續")
        except ValueError as e:
            record("TC-06a", "chat() 錯誤 model 靜默失敗", "PASS",
                   f"正確拋出 ValueError: {e}")
        except Exception as e:
            record("TC-06a", "chat() 錯誤 model 靜默失敗", "ERROR", str(e))

        # ──────────────────────────────────────────────────────
        # TC-09: current_model()
        # ──────────────────────────────────────────────────────
        print("\n── TC-09: current_model() ──")
        try:
            cm = ai.current_model()
            if cm and isinstance(cm, str):
                record("TC-09", "current_model()", "PASS", f"當前模型: {cm}", cm)
            else:
                record("TC-09", "current_model()", "FAIL", f"返回值: {cm!r}")
        except Exception as e:
            record("TC-09", "current_model()", "ERROR", str(e))

        # ──────────────────────────────────────────────────────
        # TC-03b/c + TC-06b: get_models() + 模型切換（繼續同一聊天室）
        # ──────────────────────────────────────────────────────
        print("\n── TC-03b: get_models()（AI 頁面上）──")
        try:
            t0 = time.time()
            models = ai.get_models()
            elapsed = time.time() - t0
            if models:
                record("TC-03b", "get_models()（AI 頁面）", "PASS",
                       f"返回 {len(models)} 個模型，耗時 {elapsed:.1f}s", str(models))
                selected = [m for m in models if m.get("selected")]
                if len(selected) == 1:
                    record("TC-03c", "get_models() selected 唯一", "PASS",
                           f"當前模型: {selected[0]['name']}")
                else:
                    record("TC-03c", "get_models() selected 唯一", "FAIL",
                           f"selected 數量: {len(selected)}（預期 1）")

                target_model = models[0]["name"]
                try:
                    t0 = time.time()
                    reply_m2 = "".join(ai.chat(prompt="回覆「模型切換OK」", model=target_model, timeout=30))
                    elapsed = time.time() - t0
                    record("TC-06b", f"chat() 正確 model ({target_model})", "PASS",
                           f"耗時 {elapsed:.1f}s", reply_m2[:100] if reply_m2 else "")
                except Exception as e:
                    record("TC-06b", f"chat() 正確 model ({target_model})", "ERROR", str(e))
            else:
                record("TC-03b", "get_models()（AI 頁面）", "FAIL",
                       f"返回空列表，耗時 {elapsed:.1f}s")
        except Exception as e:
            record("TC-03b", "get_models()（AI 頁面）", "ERROR", str(e))

        # ──────────────────────────────────────────────────────
        # TC-07: get_messages()（在同一聊天室讀取歷史）
        # ──────────────────────────────────────────────────────
        print("\n── TC-07: get_messages() ──")
        if ai._current_url:
            try:
                t0 = time.time()
                messages = ai.get_messages()
                elapsed = time.time() - t0
                if messages:
                    roles = [m.get("role") for m in messages]
                    record("TC-07a", "get_messages() 返回值", "PASS",
                           f"返回 {len(messages)} 條訊息，耗時 {elapsed:.1f}s，角色: {roles[:6]}",
                           str(messages[:2]))
                    alternating = all(
                        messages[i]["role"] != messages[i+1]["role"]
                        for i in range(len(messages)-1)
                    ) if len(messages) > 1 else True
                    if alternating:
                        record("TC-07b", "get_messages() 角色交替", "PASS")
                    else:
                        record("TC-07b", "get_messages() 角色交替", "FAIL",
                               f"角色未交替: {roles[:8]}")
                else:
                    record("TC-07a", "get_messages() 返回值", "FAIL",
                           f"返回空列表，耗時 {elapsed:.1f}s")
            except Exception as e:
                record("TC-07a", "get_messages()", "ERROR", str(e))
        else:
            record("TC-07a", "get_messages()", "ERROR",
                   "跳過：_current_url 為 None（先前 chat() 全部失敗）")

        # TC-10 在 TC-08 close() 之後才能跑（Playwright sync API 限制：同一 process 只能有一個 instance）
        # 此處僅做靜態結構驗證
        print("\n── TC-10: context manager（with 語法）── （在 TC-08 close 後執行）")

        # ──────────────────────────────────────────────────────
        # TC-08: close()
        # ──────────────────────────────────────────────────────
        print("\n── TC-08: close() ──")
        try:
            ai.close()
            if ai._page is None and ai._ctx is None:
                record("TC-08a", "close() 資源清理", "PASS")
            else:
                record("TC-08a", "close() 資源清理", "FAIL",
                       "_page 或 _ctx 未被清為 None")
        except Exception as e:
            record("TC-08a", "close()", "ERROR", str(e))

        # close() 後呼叫 chat() 應立刻拋 RuntimeError
        try:
            ai.chat(prompt="test")
            record("TC-08b", "close() 後呼叫 chat()", "FAIL",
                   "預期 RuntimeError 但沒有拋出")
        except RuntimeError:
            record("TC-08b", "close() 後呼叫 chat()", "PASS", "正確拋出 RuntimeError")
        except Exception as e:
            record("TC-08b", "close() 後呼叫 chat()", "ERROR", str(e))

        # ──────────────────────────────────────────────────────
        # TC-10: context manager（with 語法）
        # 主 session 已 close()，可以啟動第二個 Playwright instance
        # 只驗證 lifecycle（不送訊息，不建新聊天室）
        # ──────────────────────────────────────────────────────
        print("\n── TC-10: context manager（with 語法）──")
        try:
            with NotionAI(headless=False, debug=False) as test_ai:
                assert test_ai._page is not None, "__enter__ 後 _page 應不為 None"
            assert test_ai._page is None, "__exit__ 後 _page 應為 None"
            record("TC-10", "context manager（with 語法）", "PASS",
                   "__enter__ 回傳 self，__exit__ 正確清理資源")
        except Exception as e:
            record("TC-10", "context manager（with 語法）", "ERROR",
                   f"{e}\n{traceback.format_exc()}")

    except Exception as e:
        print(f"\n[FATAL] 測試中止: {e}")
        traceback.print_exc()
        try:
            if ai:
                ai.close()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────
    # 輸出 Markdown 報告
    # ──────────────────────────────────────────────────────
    write_report()


def write_report():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    lines = [
        "# Notion AI API — 功能測試報告",
        "",
        f"**測試時間**: {now}",
        "**環境**: Python 3.14.2 / Playwright 1.58.0 / macOS",
        f"**結果彙總**: {total} 項測試 | ✅ {passed} PASS | ❌ {failed} FAIL | ⚠️ {errors} ERROR",
        "",
        "---",
        "",
        "## 測試案例結果",
        "",
        "| 案例 | 名稱 | 結果 | 說明 |",
        "|------|------|------|------|",
    ]
    for r in results:
        icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}.get(r["status"], "?")
        detail = r["detail"].replace("|", "\\|").replace("\n", " ")[:120]
        lines.append(f"| {r['tc']} | {r['name']} | {icon} {r['status']} | {detail} |")

    lines += [
        "",
        "---",
        "",
        "## 實際輸出（非空項目）",
        "",
    ]
    for r in results:
        if r["output"]:
            lines += [
                f"### {r['tc']} — {r['name']}",
                "```",
                r["output"][:500],
                "```",
                "",
            ]

    lines += [
        "---",
        "",
        "## 代碼潛在問題清單",
        "",
        "> 標記 ✅已修復 表示此版 notion_ai.py 已內建修復；標記 ❌仍存在 表示問題尚未解決。",
        "",
        "### 🔴 HIGH — 高嚴重性",
        "",
        "| ID | 狀態 | 問題 | 位置 | 說明 | 觸發條件 |",
        "|----|------|------|------|------|---------|",
        "| P5 | ❌仍存在 | `list_chats()` 不返回 URL | `_JS_LIST_CHATS` | 返回 `{title, time, active, react_id}` 無 URL，無法跳回特定聊天室 | 嘗試用列表操作特定對話 |",
        "| P2 | ✅已修復 | STOP 按鈕競態條件 | — | 改用 `Copy response aria-disabled` 偵測完成 | — |",
        "| P3 | ✅已修復 | `_open_history_panel()` 非冪等 | — | 加入 `_is_history_panel_open()` 冪等守衛 | — |",
        "| P4 | ✅已修復 | `_set_model()` 靜默吞噬 ValueError | — | ValueError 移到 try 外，正確拋出 | — |",
        "| P24 | ✅已修復 | `_create_new_conversation()` URL 問題 | — | 直接 goto /ai，不再依賴 Start new chat 按鈕 | — |",
        "| P25 | ✅已修復 | `get_models()` 返回重複項目 | — | `_JS_MODEL_NAMES` 加入 seen Set 去重 | — |",
        "",
        "### 🟡 MEDIUM — 中嚴重性",
        "",
        "| ID | 狀態 | 問題 | 位置 | 說明 | 觸發條件 |",
        "|----|------|------|------|------|---------|",
        "| P26 | ❌仍存在 | `_close_history_panel()` 關閉不確認 | `notion_ai.py:452-462` | 點擊 toggle 後不驗證面板是否真的關閉，可能殘留開著 | 點擊事件被攔截或動畫未完成 |",
        "| P27 | ❌仍存在 | STOP 等待 10 秒不足 | `notion_ai.py:485` | 慢網路 AI 可能超 10 秒才出現 STOP；靜默 pass 後 Copy response 等待需扛住全程 | 慢網路 + API 排隊 |",
        "| P11 | ❌仍存在 | `[role=\"menuitem\"]` 選擇器過廣 | `_JS_LIST_CHATS:3` | 非聊天 menuitem 污染結果；Notion 改 ARIA 角色整個查詢失效 | DOM 含其他 menuitem |",
        "| P13 | ❌仍存在 | `start()` 過早偵測 session | `notion_ai.py:249` | `wait_until=\"load\"` 後 SPA 可能仍在 redirect，`/login` 檢查誤判 | SPA redirect 比 load 慢 |",
        "| P14 | ❌仍存在 | session 過期只偵測 `/login` | `notion_ai.py:249` | 也可能重導向 `/sign-up`、`/select-workspace` | 特定帳號狀態 |",
        "| P10 | ✅已修復 | `execCommand` 已廢棄 | — | 改用 `keyboard.type()` | — |",
        "| P15 | ✅已修復 | `close()` 無 try/finally | — | 已加入 try/finally | — |",
        "| P16 | ✅已修復 | `get_models()` 無頁面守衛 | — | 已加入 `_ensure_ai_page()` | — |",
        "",
        "### 🟢 LOW — 低嚴重性",
        "",
        "| ID | 狀態 | 問題 | 位置 | 說明 |",
        "|----|------|------|------|------|",
        "| P18 | ❌仍存在 | sort `pos=0` 不穩定 | `_JS_GET_ALL_MESSAGES` sort | `compareDocumentPosition()` 返回 0 時排序不穩定 |",
        "| P19 | ❌仍存在 | listitem fallback 角色判斷 | `_JS_GET_ALL_MESSAGES` | `contenteditable` 送出後可能消失，全判為 assistant |",
        "| P28 | ❌仍存在 | `_navigate()` 無超時守衛 | `notion_ai.py:427-430` | `wait_for_selector` 固定 15 秒，頁面加載失敗無法提早偵測 |",
        "| P29 | ❌仍存在 | `_set_model()` 兩次開關選單 | `notion_ai.py:510-519` | 先 `get_models()`（開＋關），再 `page.click(SEL_MODEL)`（重開）；慢頁面可能錯位 |",
        "",
        "---",
        "",
        "## 修復優先建議",
        "",
        "1. **HIGH — 功能完整性**",
        "   - **P5**: `_JS_LIST_CHATS` 補上 href/URL 欄位，讓 `list_chats()` 結果可直接用於導航特定對話",
        "",
        "2. **MEDIUM — 穩定性**",
        "   - **P26**: `_close_history_panel()` 關閉後用 `_is_history_panel_open()` 確認，若仍開著再 Escape",
        "   - **P27**: `_wait_for_reply_complete()` 的 STOP 等待從 10 秒延長至 30 秒（慢網路緩衝）",
        "   - **P11**: `_JS_LIST_CHATS` 改用 `svg.chatBubble` 過濾確認（已有），但需驗證 Notion 版本相容性",
        "   - **P13/P14**: `start()` 加入更多 redirect 路徑偵測，並考慮等待 `wait_for_load_state('networkidle')`",
        "",
        "3. **LOW — 邊界情況**",
        "   - **P18**: sort 加入 tiebreaker（如 DOM index）",
        "   - **P29**: `_set_model()` 合併為一次選單操作：先打開，驗證目標不在清單才 close + raise",
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 報告已輸出至 {REPORT_PATH.resolve()}")


if __name__ == "__main__":
    run_tests()
