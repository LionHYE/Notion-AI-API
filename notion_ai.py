"""
Notion AI — headless Playwright client.

Setup (once):
    python setup_auth.py     # logs you in and saves notion_auth.json

Usage:
    from notion_ai import NotionAI

    ai = NotionAI("notion_auth.json")
    ai.start()

    # 列出所有聊天室
    chats = ai.list_chats()

    # 獲取某個聊天室的訊息
    messages = ai.get_messages("https://www.notion.so/ai/...")

    # 一般對話（自動創建新聊天室）
    reply = ai.chat(prompt="你好")

    # 多輪對話（繼續同一聊天室）
    reply1 = ai.chat(prompt="我叫小明")
    reply2 = ai.chat(prompt="我叫什麼名字？")  # 繼續同一聊天室

    # 指定聊天室繼續對話
    reply = ai.chat(prompt="繼續討論", chat="https://www.notion.so/ai/...")

    ai.close()
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Optional, Dict, List, Any

from playwright.sync_api import sync_playwright, Page, BrowserContext, Playwright

# ── Selectors ──────────────────────────────────────────────────────────────────

SEL_INPUT   = '[id=":r61:"]'
SEL_INPUT_F = '[role="textbox"][contenteditable="true"]'
SEL_SEND    = '[data-testid="agent-send-message-button"]'
SEL_STOP    = '[data-testid="agent-stop-inference-button"]'
SEL_MODEL   = '[data-testid="unified-chat-model-button"]'
SEL_MENU    = '[role="menu"]'
SEL_ITEM    = '[role="menuitem"]'
SEL_HISTORY = '[aria-label="對話記錄"], [aria-label="Chat history"], [aria-label*="chat"], [aria-label*="history"], svg.chatBubble'
SEL_NEW_CHAT = '[aria-label="開啟新對話"], [aria-label="New chat"]'

# ── Inline JS helpers ──────────────────────────────────────────────────────────

_JS_TYPE = """
(text) => {
    const el = document.querySelector('%s') || document.querySelector('%s');
    if (!el) throw new Error('Notion AI input box not found. Open a Notion AI chat page first.');
    el.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('delete',    false, null);
    document.execCommand('insertText', false, text);
}
""" % (SEL_INPUT, SEL_INPUT_F)

_JS_GET_REPLY = """
async () => {
    const btns = [
        ...document.querySelectorAll('[role="button"][aria-label*="複製"]'),
        ...document.querySelectorAll('[role="button"][aria-label*="Copy"]'),
        ...document.querySelectorAll('[aria-label*="copy"]'),
        ...document.querySelectorAll('[aria-label*="複製"]'),
    ];

    if (btns.length) {
        const last = btns[btns.length - 1];
        try {
            const clipboardResult = await new Promise((resolve) => {
                navigator.clipboard.writeText = text => { resolve(text); return Promise.resolve(); };
                navigator.clipboard.write = items => {
                    Promise.all((items || []).map(item => {
                        const t = item.types.find(t => t === 'text/plain');
                        return t ? item.getType(t).then(b => b.text()) : Promise.resolve('');
                    })).then(parts => resolve(parts.join('')));
                    return Promise.resolve();
                };
                last.click();
                setTimeout(() => resolve(null), 2000);
            });
            if (clipboardResult) return clipboardResult;
        } catch (e) {}
    }

    const responseElements = [
        ...document.querySelectorAll('[data-testid="agent-response"]'),
        ...document.querySelectorAll('[data-testid*="response"]'),
        ...document.querySelectorAll('[class*="response"]'),
    ];
    if (responseElements.length) {
        const last = responseElements[responseElements.length - 1];
        return last.innerText || last.textContent;
    }

    const messages = document.querySelectorAll('[class*="message"], [role="listitem"]');
    const aiMessages = Array.from(messages).filter(msg =>
        !msg.querySelector('[contenteditable="true"]') &&
        ((msg.getAttribute('class') || '').includes('ai') ||
         (msg.getAttribute('data-testid') || '').includes('agent'))
    );
    if (aiMessages.length) {
        const last = aiMessages[aiMessages.length - 1];
        return last.innerText || last.textContent;
    }

    return null;
}
"""

_JS_GET_ALL_MESSAGES = """
() => {
    const result = [];

    // 嘗試獲取所有對話訊息（user + assistant）
    const userMsgs = document.querySelectorAll('[data-testid="agent-user-message"], [class*="userMessage"], [class*="user-message"]');
    const aiMsgs   = document.querySelectorAll('[data-testid="agent-response"], [class*="aiMessage"], [class*="ai-message"]');

    // 如果能找到分開的節點，合併後按 DOM 順序排列
    if (userMsgs.length || aiMsgs.length) {
        const all = [
            ...Array.from(userMsgs).map(el => ({ role: 'user',      el })),
            ...Array.from(aiMsgs).map(el  => ({ role: 'assistant',  el })),
        ];
        // 按 DOM 位置排序
        all.sort((a, b) => {
            const pos = a.el.compareDocumentPosition(b.el);
            return pos & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
        });
        return all.map(({ role, el }) => ({ role, content: (el.innerText || el.textContent || '').trim() }));
    }

    // fallback：抓所有 listitem，嘗試依結構猜測角色
    const items = document.querySelectorAll('[role="listitem"]');
    return Array.from(items).map(item => {
        const isUser = !!item.querySelector('[contenteditable="true"]') ||
                       (item.getAttribute('class') || '').toLowerCase().includes('user');
        return {
            role: isUser ? 'user' : 'assistant',
            content: (item.innerText || item.textContent || '').trim(),
        };
    }).filter(m => m.content);
}
"""

_JS_CURRENT_MODEL = """
() => {
    const btn = document.querySelector('%s');
    if (!btn) return null;
    const leaves = [...btn.querySelectorAll('div')].filter(d => !d.children.length && d.textContent.trim());
    const name   = leaves.find(d => {
        const t = d.textContent.trim();
        return t && t !== '測試版' && t !== 'Beta' && t.length > 1;
    });
    return name ? name.textContent.trim() : null;
}
""" % SEL_MODEL

_JS_MODEL_NAMES = """
() => {
    const items = [...document.querySelectorAll('%s')];
    return items.map(item => {
        const leaves   = [...item.querySelectorAll('div')].filter(d => !d.children.length && d.textContent.trim());
        const namePart = leaves.find(d => { const t = d.textContent.trim(); return t && t !== '測試版' && t !== 'Beta' && t.length > 1; });
        const selected = !!item.querySelector('[class*="checkmark"]');
        return namePart ? { name: namePart.textContent.trim(), selected } : null;
    }).filter(Boolean);
}
""" % SEL_ITEM

_JS_LIST_CHATS = """
() => {
    const items = [
        ...document.querySelectorAll('[role="menuitem"]'),
        ...document.querySelectorAll('[class*="chatItem"]'),
        ...document.querySelectorAll('[class*="conversation"]'),
    ];
    return items.map(item => {
        const titleEl = item.querySelector('[style*="font-size: 14px"]') ||
                        item.querySelector('[style*="font-weight: 500"]') ||
                        item.querySelector('[class*="title"]');
        const timeEl  = item.querySelector('[style*="font-size: 12px"]') ||
                        item.querySelector('[class*="time"]');
        if (!titleEl) return null;
        const isActive = (item.getAttribute('style') || '').includes('background') ||
                         (item.getAttribute('class') || '').includes('active');
        return {
            title:  titleEl.innerText.trim(),
            time:   timeEl ? timeEl.innerText.trim() : '',
            active: isActive,
        };
    }).filter(Boolean);
}
"""

class NotionAI:
    """Headless Playwright wrapper for Notion AI.

    Keeps the browser open for the lifetime of the object — call close() when done.
    Supports one-off chats and multi-turn conversations in the same function.
    """

    def __init__(
        self,
        auth_path: str | Path = "notion_auth.json",
        headless:  bool       = True,
        debug:     bool       = False,
    ):
        self._auth_path = Path(auth_path)
        self._headless  = headless
        self._debug     = debug
        self._pw:   Optional[Playwright]     = None
        self._ctx:  Optional[BrowserContext] = None
        self._page: Optional[Page]           = None
        self._current_url: Optional[str]     = None  # URL of the active conversation

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        if self._debug:
            print(f"[NotionAI] {msg}", flush=True)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> "NotionAI":
        if not self._auth_path.exists():
            raise FileNotFoundError(
                f"找不到 {self._auth_path}，請先執行：python setup_auth.py"
            )
        print("[NotionAI] 正在啟動 Chromium…", flush=True)
        self._pw  = sync_playwright().__enter__()
        browser   = self._pw.chromium.launch(headless=self._headless)
        self._ctx = browser.new_context(storage_state=str(self._auth_path))
        self._page = self._ctx.new_page()
        print("[NotionAI] Chromium 已啟動", flush=True)

        self._page.goto("https://www.notion.so", wait_until="domcontentloaded")
        if "/login" in self._page.url:
            self.close()
            raise PermissionError(
                "Notion session 已過期，請重新執行：python setup_auth.py"
            )
        self._log("Session 驗證成功")
        return self

    def close(self) -> None:
        print("[NotionAI] 正在關閉 Chromium…", flush=True)
        if self._ctx:  self._ctx.close()
        if self._pw:   self._pw.stop()
        self._ctx = self._page = self._pw = None
        print("[NotionAI] Chromium 已關閉", flush=True)

    def __enter__(self) -> "NotionAI":
        return self.start()

    def __exit__(self, *_) -> None:
        self.close()

    # ── Public API ─────────────────────────────────────────────────────────────

    def list_chats(self) -> List[Dict[str, Any]]:
        """列出所有聊天室。

        Returns:
            [{'title': str, 'time': str, 'active': bool}, ...]
        """
        page = self._assert_started()
        self._log("正在獲取聊天室列表…")
        try:
            self._open_history_panel()
            chats = page.evaluate(_JS_LIST_CHATS)
            page.keyboard.press("Escape")
            return chats
        except Exception as e:
            self._log(f"獲取聊天室列表失敗: {e}")
            page.keyboard.press("Escape")
            return []

    def get_messages(self, chat: str) -> List[Dict[str, str]]:
        """獲取某個聊天室的對話訊息。

        Args:
            chat: 聊天室的 URL 或 ID（如 "https://www.notion.so/ai/..."）。

        Returns:
            [{'role': 'user'|'assistant', 'content': str}, ...]
        """
        page = self._assert_started()
        url  = self._resolve_chat_url(chat)
        self._log(f"正在載入聊天室: {url}")
        self._navigate(url)
        page.wait_for_timeout(1500)
        messages = page.evaluate(_JS_GET_ALL_MESSAGES)
        self._log(f"獲取到 {len(messages)} 條訊息")
        return messages

    def chat(
        self,
        prompt:  str,
        *,
        chat:    Optional[str] = None,
        model:   Optional[str] = None,
        timeout: int           = 120,
    ) -> str:
        """與 Notion AI 對話，返回 AI 回覆文字。

        若不提供 `chat`，則繼續目前已開啟的聊天室；若尚無聊天室，則自動建立新的。
        若提供 `chat`，則切換到指定聊天室後發送訊息（多輪對話：之後再呼叫時不提供
        `chat` 即可繼續同一聊天室）。

        Args:
            prompt:  要發送的訊息。
            chat:    聊天室 URL 或 ID（可選）。
            model:   模型名稱，例如 "Opus 4.7"、"Sonnet 4.6"、"自動"。
            timeout: 等待 AI 回覆完成的秒數上限。

        Returns:
            AI 的回覆文字。
        """
        page = self._assert_started()

        # 決定目標 URL
        if chat:
            target_url = self._resolve_chat_url(chat)
            if self._page.url != target_url:
                self._log(f"切換到指定聊天室: {target_url}")
                self._navigate(target_url)
            self._current_url = target_url
        elif self._current_url:
            # 繼續目前聊天室（不重新導航，保留對話狀態）
            if self._page.url != self._current_url:
                self._log(f"回到當前聊天室: {self._current_url}")
                self._navigate(self._current_url)
            self._log("繼續目前聊天室")
        else:
            self._log("無活躍聊天室，建立新聊天室")
            self._create_new_conversation()

        if model:
            self._set_model(model)

        self._type_message(prompt)

        page.wait_for_function(
            f"() => {{ const b = document.querySelector('{SEL_SEND}'); return b && b.getAttribute('aria-disabled') !== 'true'; }}",
            timeout=5_000,
        )
        page.click(SEL_SEND)

        try:
            page.wait_for_selector(SEL_STOP, timeout=8_000)
        except Exception:
            pass

        try:
            page.wait_for_selector(SEL_STOP, state="hidden", timeout=timeout * 1_000)
        except Exception:
            page.wait_for_timeout(5_000)

        # 發送後 URL 可能已更新（第一次發送時 Notion 會分配新 URL）
        self._current_url = page.url

        for _ in range(3):
            reply = self._get_reply()
            if reply:
                return reply
            page.wait_for_timeout(1_000)

        raise RuntimeError("回覆擷取失敗：無法獲取 AI 回覆文字。")

    def get_models(self) -> List[Dict[str, Any]]:
        """返回可用模型清單：[{'name': str, 'selected': bool}, ...]"""
        page = self._assert_started()
        try:
            page.click(SEL_MODEL)
            page.wait_for_selector(SEL_MENU, timeout=3_000)
            models = page.evaluate(_JS_MODEL_NAMES)
            page.keyboard.press("Escape")
            return models
        except Exception as e:
            self._log(f"獲取模型列表失敗: {e}")
            return []

    # ── Private helpers ────────────────────────────────────────────────────────

    def _assert_started(self) -> Page:
        if not self._page:
            raise RuntimeError("請先呼叫 start()，或使用 `with NotionAI(...) as ai:` 語法。")
        return self._page

    def _resolve_chat_url(self, chat: str) -> str:
        """將聊天室 ID 或完整 URL 統一轉換為完整 URL。"""
        chat = chat.strip()
        if chat.startswith("http"):
            return chat
        # 假設是純 ID，拼接完整路徑
        return f"https://www.notion.so/ai/{chat}"

    def _navigate(self, url: str) -> None:
        self._log(f"導航到: {url}")
        self._page.goto(url, wait_until="load")
        self._page.wait_for_selector(f"{SEL_INPUT}, {SEL_INPUT_F}", timeout=15_000)

    def _create_new_conversation(self) -> None:
        page = self._page
        try:
            self._open_history_panel()
            page.click(SEL_NEW_CHAT)
            page.wait_for_selector(f"{SEL_INPUT}, {SEL_INPUT_F}", timeout=15_000)
        except Exception as e:
            self._log(f"UI 方式建立新聊天室失敗: {e}，改用直接導航")
            page.goto("https://www.notion.so/ai", wait_until="load")
            page.wait_for_selector(f"{SEL_INPUT}, {SEL_INPUT_F}", timeout=15_000)
        self._current_url = page.url
        self._log(f"新聊天室已建立: {self._current_url}")

    def _open_history_panel(self) -> None:
        page = self._page
        for selector in SEL_HISTORY.split(", "):
            try:
                if page.query_selector(selector):
                    page.click(selector)
                    break
            except Exception:
                continue
        try:
            page.wait_for_selector(SEL_MENU, timeout=5_000)
            page.wait_for_timeout(500)
        except Exception as e:
            self._log(f"等待歷史面板失敗: {e}")

    def _type_message(self, text: str) -> None:
        self._page.evaluate(_JS_TYPE, text)

    def _get_reply(self) -> Optional[str]:
        page = self._page
        try:
            vp = page.viewport_size or {"width": 1280, "height": 800}
            page.mouse.move(vp["width"] / 2, vp["height"] * 0.75)
            page.wait_for_timeout(600)
        except Exception:
            pass
        return page.evaluate(_JS_GET_REPLY)

    def _set_model(self, model_name: str) -> None:
        page = self._page
        try:
            if page.evaluate(_JS_CURRENT_MODEL) == model_name:
                return
            page.click(SEL_MODEL)
            page.wait_for_selector(SEL_MENU, timeout=3_000)
            for item in page.query_selector_all(SEL_ITEM):
                for leaf in item.query_selector_all("div"):
                    try:
                        t = leaf.inner_text().strip()
                        if t and t not in ("測試版", "Beta") and len(t) > 1:
                            if t == model_name:
                                item.click()
                                return
                            break
                    except Exception:
                        continue
            page.keyboard.press("Escape")
            raise ValueError(f'找不到 model "{model_name}"。可用: {[m["name"] for m in self.get_models()]}')
        except Exception as e:
            self._log(f"設置模型失敗: {e}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "用一句話打個招呼。"
    print(f"Prompt: {prompt}")

    with NotionAI(debug=True) as ai:
        reply = ai.chat(prompt=prompt)
        print(f"Reply : {reply}")

        if not sys.argv[1:]:
            print("\n測試多輪對話（同一聊天室，不重啟瀏覽器）…")
            r1 = ai.chat(prompt="請記住數字 42，回覆「已記住」")
            print(f"輪次 1: {r1}")
            r2 = ai.chat(prompt="我剛才請你記住什麼數字？")
            print(f"輪次 2: {r2}")
            r3 = ai.chat(prompt="把這個數字乘以 2")
            print(f"輪次 3: {r3}")
