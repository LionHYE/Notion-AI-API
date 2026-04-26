# Notion AI API — 功能測試報告

**測試時間**: 2026-04-26 06:59:37
**環境**: Python 3.14.2 / Playwright 1.58.0 / macOS
**結果彙總**: 20 項測試 | ✅ 18 PASS | ❌ 2 FAIL | ⚠️ 0 ERROR

---

## 測試案例結果

| 案例 | 名稱 | 結果 | 說明 |
|------|------|------|------|
| TC-01 | session 驗證 | ✅ PASS | 啟動成功，URL: https://www.notion.so/?cookie_sync_completed=true |
| TC-03a | get_models()（根目錄） | ✅ PASS | 返回 10 個模型，耗時 3.9s |
| TC-04a | chat() 基本回覆 | ✅ PASS | 耗時 5.8s，chunks=2，URL: https://www.notion.so/chat?t=34d892006b3b80d4bd8600a9dc06f988&wfv=chat |
| TC-04b | chat() 特殊字元 | ✅ PASS | 耗時 5.1s |
| TC-05a | 多輪第 1 輪 | ✅ PASS | URL: https://www.notion.so/chat?t=34d892006b3b80d4bd8600a9dc06f988&wfv=chat |
| TC-05b | 多輪第 2 輪（記憶） | ✅ PASS |  |
| TC-05c | 多輪第 3 輪（計算） | ❌ FAIL | 回覆未含 84 |
| TC-02a | list_chats() 首次 | ✅ PASS | 返回 50 個項目，耗時 2.9s，含 URL: False |
| TC-02a-P5 | list_chats() 缺 url 欄位 | ❌ FAIL | 返回值無 url 欄位（P5） |
| TC-02b | list_chats() 連續第二次 | ✅ PASS | 返回 50 個項目，耗時 0.0s |
| TC-06a | chat() 錯誤 model 靜默失敗 | ✅ PASS | 正確拋出 ValueError: 找不到 model "完全不存在的模型XYZ"。可用: ['自動', 'Sonnet 4.6', 'Opus 4.6', 'Opus 4.7', 'Gemini 3.1 Pro', 'GPT-5.2', ' |
| TC-09 | current_model() | ✅ PASS | 當前模型: 自動 |
| TC-03b | get_models()（AI 頁面） | ✅ PASS | 返回 10 個模型，耗時 0.3s |
| TC-03c | get_models() selected 唯一 | ✅ PASS | 當前模型: 自動 |
| TC-06b | chat() 正確 model (自動) | ✅ PASS | 耗時 31.4s |
| TC-07a | get_messages() 返回值 | ✅ PASS | 返回 2 條訊息，耗時 0.0s，角色: ['user', 'assistant'] |
| TC-07b | get_messages() 角色交替 | ✅ PASS |  |
| TC-08a | close() 資源清理 | ✅ PASS |  |
| TC-08b | close() 後呼叫 chat() | ✅ PASS | 正確拋出 RuntimeError |
| TC-10 | context manager（with 語法） | ✅ PASS | __enter__ 回傳 self，__exit__ 正確清理資源 |

---

## 實際輸出（非空項目）

### TC-03a — get_models()（根目錄）
```
[{'name': '自動', 'selected': True}, {'name': 'Sonnet 4.6', 'selected': False}, {'name': 'Opus 4.6', 'selected': False}, {'name': 'Opus 4.7', 'selected': False}, {'name': 'Gemini 3.1 Pro', 'selected': False}, {'name': 'GPT-5.2', 'selected': False}, {'name': 'GPT-5.4', 'selected': False}, {'name': 'GPT-5.5', 'selected': False}, {'name': 'Kimi K2.6', 'selected': False}, {'name': 'Gemini 2.5 Flash', 'selected': False}]
```

### TC-04a — chat() 基本回覆
```
早安，Lion——今天也一起把想做的事穩穩推進。
```

### TC-04b — chat() 特殊字元
```
早安，Lion——今天也一起把想做的事穩穩推進。
```

### TC-05a — 多輪第 1 輪
```
Hello 世界 🌏
```

### TC-05b — 多輪第 2 輪（記憶）
```
已記住請我記住的數字是 42。
```

### TC-05c — 多輪第 3 輪（計算）
```
你剛才請我記住的數字是 42。
```

### TC-02a — list_chats() 首次
```
[{'title': '一句话打招呼', 'time': '剛剛發生', 'active': False, 'react_id': ':r2g:'}, {'title': '記住數字42', 'time': '12 分鐘前', 'active': False, 'react_id': ':r2h:'}, {'title': '輸出 Hello 世界 🌏', 'time': '13 分鐘前', 'active': False, 'react_id': ':r2i:'}]
```

### TC-09 — current_model()
```
自動
```

### TC-03b — get_models()（AI 頁面）
```
[{'name': '自動', 'selected': True}, {'name': 'Sonnet 4.6', 'selected': False}, {'name': 'Opus 4.6', 'selected': False}, {'name': 'Opus 4.7', 'selected': False}, {'name': 'Gemini 3.1 Pro', 'selected': False}, {'name': 'GPT-5.2', 'selected': False}, {'name': 'GPT-5.4', 'selected': False}, {'name': 'GPT-5.5', 'selected': False}, {'name': 'Kimi K2.6', 'selected': False}, {'name': 'Gemini 2.5 Flash', 'selected': False}]
```

### TC-06b — chat() 正確 model (自動)
```
模型切換OK
```

### TC-07a — get_messages() 返回值
```
[{'role': 'user', 'content': '回覆「模型切換OK」', 'id': '34d89200-6b3b-803c-9068-00aad0aaf16b'}, {'role': 'assistant', 'content': '模型切換OK', 'id': None}]
```

---

## 代碼潛在問題清單

> 標記 ✅已修復 表示此版 notion_ai.py 已內建修復；標記 ❌仍存在 表示問題尚未解決。

### 🔴 HIGH — 高嚴重性

| ID | 狀態 | 問題 | 位置 | 說明 | 觸發條件 |
|----|------|------|------|------|---------|
| P5 | ❌仍存在 | `list_chats()` 不返回 URL | `_JS_LIST_CHATS` | 返回 `{title, time, active, react_id}` 無 URL，無法跳回特定聊天室 | 嘗試用列表操作特定對話 |
| P2 | ✅已修復 | STOP 按鈕競態條件 | — | 改用 `Copy response aria-disabled` 偵測完成 | — |
| P3 | ✅已修復 | `_open_history_panel()` 非冪等 | — | 加入 `_is_history_panel_open()` 冪等守衛 | — |
| P4 | ✅已修復 | `_set_model()` 靜默吞噬 ValueError | — | ValueError 移到 try 外，正確拋出 | — |
| P24 | ✅已修復 | `_create_new_conversation()` URL 問題 | — | 直接 goto /ai，不再依賴 Start new chat 按鈕 | — |
| P25 | ✅已修復 | `get_models()` 返回重複項目 | — | `_JS_MODEL_NAMES` 加入 seen Set 去重 | — |

### 🟡 MEDIUM — 中嚴重性

| ID | 狀態 | 問題 | 位置 | 說明 | 觸發條件 |
|----|------|------|------|------|---------|
| P26 | ❌仍存在 | `_close_history_panel()` 關閉不確認 | `notion_ai.py:452-462` | 點擊 toggle 後不驗證面板是否真的關閉，可能殘留開著 | 點擊事件被攔截或動畫未完成 |
| P27 | ❌仍存在 | STOP 等待 10 秒不足 | `notion_ai.py:485` | 慢網路 AI 可能超 10 秒才出現 STOP；靜默 pass 後 Copy response 等待需扛住全程 | 慢網路 + API 排隊 |
| P11 | ❌仍存在 | `[role="menuitem"]` 選擇器過廣 | `_JS_LIST_CHATS:3` | 非聊天 menuitem 污染結果；Notion 改 ARIA 角色整個查詢失效 | DOM 含其他 menuitem |
| P13 | ❌仍存在 | `start()` 過早偵測 session | `notion_ai.py:249` | `wait_until="load"` 後 SPA 可能仍在 redirect，`/login` 檢查誤判 | SPA redirect 比 load 慢 |
| P14 | ❌仍存在 | session 過期只偵測 `/login` | `notion_ai.py:249` | 也可能重導向 `/sign-up`、`/select-workspace` | 特定帳號狀態 |
| P10 | ✅已修復 | `execCommand` 已廢棄 | — | 改用 `keyboard.type()` | — |
| P15 | ✅已修復 | `close()` 無 try/finally | — | 已加入 try/finally | — |
| P16 | ✅已修復 | `get_models()` 無頁面守衛 | — | 已加入 `_ensure_ai_page()` | — |

### 🟢 LOW — 低嚴重性

| ID | 狀態 | 問題 | 位置 | 說明 |
|----|------|------|------|------|
| P18 | ❌仍存在 | sort `pos=0` 不穩定 | `_JS_GET_ALL_MESSAGES` sort | `compareDocumentPosition()` 返回 0 時排序不穩定 |
| P19 | ❌仍存在 | listitem fallback 角色判斷 | `_JS_GET_ALL_MESSAGES` | `contenteditable` 送出後可能消失，全判為 assistant |
| P28 | ❌仍存在 | `_navigate()` 無超時守衛 | `notion_ai.py:427-430` | `wait_for_selector` 固定 15 秒，頁面加載失敗無法提早偵測 |
| P29 | ❌仍存在 | `_set_model()` 兩次開關選單 | `notion_ai.py:510-519` | 先 `get_models()`（開＋關），再 `page.click(SEL_MODEL)`（重開）；慢頁面可能錯位 |

---

## 修復優先建議

1. **HIGH — 功能完整性**
   - **P5**: `_JS_LIST_CHATS` 補上 href/URL 欄位，讓 `list_chats()` 結果可直接用於導航特定對話

2. **MEDIUM — 穩定性**
   - **P26**: `_close_history_panel()` 關閉後用 `_is_history_panel_open()` 確認，若仍開著再 Escape
   - **P27**: `_wait_for_reply_complete()` 的 STOP 等待從 10 秒延長至 30 秒（慢網路緩衝）
   - **P11**: `_JS_LIST_CHATS` 改用 `svg.chatBubble` 過濾確認（已有），但需驗證 Notion 版本相容性
   - **P13/P14**: `start()` 加入更多 redirect 路徑偵測，並考慮等待 `wait_for_load_state('networkidle')`

3. **LOW — 邊界情況**
   - **P18**: sort 加入 tiebreaker（如 DOM index）
   - **P29**: `_set_model()` 合併為一次選單操作：先打開，驗證目標不在清單才 close + raise
