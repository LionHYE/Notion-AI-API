"""
Notion AI — headless Playwright client.

Setup (once):
    python setup_auth.py     # logs you in and saves notion_auth.json

Usage:
    from notion_ai import NotionAI

    with NotionAI(debug=True) as ai:
        # 串流對話（逐段印出，像 ChatGPT 打字效果）
        for chunk in ai.chat(prompt="你好"):
            print(chunk, end="", flush=True)

        # 非串流（取完整字串）
        reply = ai.chat_sync(prompt="你好")
        # 或等價的：reply = "".join(ai.chat(prompt="你好"))

        # 多輪對話（留在同一聊天室）
        "".join(ai.chat(prompt="我養了一隻叫 Mochi 的貓"))
        "".join(ai.chat(prompt="我剛才說的貓叫什麼？"))

        # 進入指定聊天室（URL / react_id / 標題皆可）
        "".join(ai.chat(prompt="繼續", room="聊天室標題"))

        # 列出所有聊天室
        chats = ai.list_chats()

        # 抓當前聊天室的全部訊息
        msgs  = ai.get_messages()

        # 模型
        models = ai.get_models()
        "".join(ai.chat(prompt="換模型試試", model="Opus 4.7"))
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Dict, List, Any, Iterator

from playwright.sync_api import (
    sync_playwright,
    Page,
    BrowserContext,
    Playwright,
    TimeoutError as PWTimeout,
)

# ── URLs ───────────────────────────────────────────────────────────────────────

HOME_URL = "https://www.notion.so/"
AI_URL   = "https://www.notion.so/ai"

# ── Selectors（Session 1.5~1.8 最終版）────────────────────────────────────────

# 輸入框：data-content-editable-leaf + role=textbox（穩定，不依賴動態 React id）
SEL_INPUT       = '[data-content-editable-leaf="true"][role="textbox"]'
SEL_INPUT_F     = '[role="textbox"][contenteditable="true"]'

SEL_SEND        = '[data-testid="agent-send-message-button"]'
SEL_STOP        = '[data-testid="agent-stop-inference-button"]'
SEL_MODEL       = '[data-testid="unified-chat-model-button"]'
SEL_MENU        = '[role="menu"][aria-activedescendant]'
SEL_ITEM        = '[role="menuitem"]'
SEL_COPY_RESP   = '[aria-label="Copy response"], [aria-label="複製回應"]'
SEL_HISTORY_BTN = '[aria-label="Chat history"], [aria-label="對話記錄"]'

# ── Inline JS helpers ──────────────────────────────────────────────────────────

# 聊天室列表：只抓含 svg.chatBubble 的 menuitem（排除分組標題/Loading 等）
_JS_LIST_CHATS = r"""
() => {
    const region = document.querySelector('[role="region"]');
    if (!region) return [];
    const items = [...region.querySelectorAll('[role="menuitem"]')]
        .filter(el => el.querySelector('svg.chatBubble'));
    return items.map(item => {
        const leaves = [...item.querySelectorAll('div')]
            .filter(d => !d.children.length && d.textContent.trim());
        const title = leaves[0]?.textContent.trim() || '';
        const time  = leaves[leaves.length - 1]?.textContent.trim() || '';
        const style = item.getAttribute('style') || '';
        const active = /background:\s*var\(--ca-bacTerTra\)/.test(style);
        return {
            title,
            time,
            active,
            react_id: item.id || null,
        };
    });
}
"""

# 模型清單：分兩區回傳
#   第一區 wrapper（menu.children[0]）= Notion AI 路由版（自動 + 各模型）
#   第二區 wrapper（menu.children[1]）= 直接和模型對話（純語言模型直連）
_JS_MODEL_NAMES = r"""
() => {
    const menu = document.querySelector('[role="menu"][aria-activedescendant]');
    if (!menu) return [];
    const out = [];
    [...menu.children].forEach((section, sectionIdx) => {
        const items = [...section.querySelectorAll('[role="menuitem"]')];
        for (const item of items) {
            const leaves = [...item.querySelectorAll('div')].filter(
                d => !d.children.length
                  && d.textContent.trim()
                  && !d.classList.contains('xamitd3'),
            );
            const name = leaves[0]?.textContent.trim();
            if (!name) continue;
            const selected = !!item.querySelector('svg.checkmarkSmall');
            out.push({ name, selected, direct: sectionIdx === 1 });
        }
    });
    return out;
}
"""

_JS_CURRENT_MODEL = r"""
() => {
    const btn = document.querySelector('[data-testid="unified-chat-model-button"]');
    if (!btn) return null;
    const leaves = [...btn.querySelectorAll('div')].filter(
        d => !d.children.length
          && d.textContent.trim()
          && !d.classList.contains('xamitd3'),
    );
    return leaves[0]?.textContent.trim() || null;
}
"""

# target: 模型名稱; direct: true=第二區直連, false/null=第一區路由版
_JS_CLICK_MODEL_ITEM = r"""
([target, direct]) => {
    const menu = document.querySelector('[role="menu"][aria-activedescendant]');
    if (!menu) return false;
    const sections = [...menu.children];
    const candidates = direct === true
        ? (sections[1] ? [...sections[1].querySelectorAll('[role="menuitem"]')] : [])
        : (sections[0] ? [...sections[0].querySelectorAll('[role="menuitem"]')] : []);
    for (const it of candidates) {
        const leaves = [...it.querySelectorAll('div')].filter(
            d => !d.children.length
              && d.textContent.trim()
              && !d.classList.contains('xamitd3'),
        );
        if (leaves[0]?.textContent.trim() === target) {
            it.click();
            return true;
        }
    }
    return false;
}
"""

# 取所有訊息：user = [data-agent-chat-user-step-id]，assistant = [data-content-editable-root="true"]
_JS_GET_ALL_MESSAGES = r"""
() => {
    function leafText(el) {
        let out = '';
        for (const node of el.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) {
                out += node.textContent;
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName;
                const inner = leafText(node);
                if (!inner) continue;
                if (tag === 'STRONG' || tag === 'B') out += `**${inner}**`;
                else if (tag === 'EM' || tag === 'I') out += `*${inner}*`;
                else if (tag === 'CODE') out += `\`${inner}\``;
                else if (tag === 'S' || tag === 'DEL') out += `~~${inner}~~`;
                else if (tag === 'A') {
                    const href = node.getAttribute('href') || '';
                    out += href ? `[${inner}](${href})` : inner;
                } else {
                    out += inner;
                }
            }
        }
        return out;
    }

    function blockToMd(block) {
        const cls = block.className || '';
        const leaf = block.querySelector('[data-content-editable-leaf="true"]');
        const pre = block.querySelector('pre') || (block.tagName === 'PRE' ? block : null);
        if (pre) {
            const langEl = block.querySelector('[class*="language-"], [data-language]');
            const lang = langEl
                ? (langEl.getAttribute('data-language') || langEl.className.match(/language-(\S+)/)?.[1] || '')
                : '';
            return '```' + lang + '\n' + pre.textContent + '\n```';
        }
        if (!leaf) return null;
        const hTag = block.querySelector('h1,h2,h3,h4,h5,h6');
        if (hTag) {
            const level = parseInt(hTag.tagName[1], 10);
            return '#'.repeat(level) + ' ' + leafText(leaf).trim();
        }
        if (block.closest('[class*="bulleted"]') || cls.includes('bulleted')
            || block.querySelector('[class*="bulletedListItem"]')) {
            return '- ' + leafText(leaf).trim();
        }
        if (block.closest('[class*="numbered"]') || cls.includes('numbered')
            || block.querySelector('[class*="numberedListItem"]')) {
            return '1. ' + leafText(leaf).trim();
        }
        if (cls.includes('quote') || block.querySelector('[class*="quote"]')) {
            return '> ' + leafText(leaf).trim();
        }
        return leafText(leaf).trim();
    }

    const results = [];
    document.querySelectorAll('[data-agent-chat-user-step-id]').forEach(step => {
        const leaf = step.querySelector('[data-content-editable-leaf="true"]');
        if (leaf) results.push({
            role: 'user',
            text: leaf.textContent,
            id:   step.getAttribute('data-agent-chat-user-step-id'),
            node: step,
        });
    });
    document.querySelectorAll('[data-content-editable-root="true"]').forEach(root => {
        if (root.closest('[data-agent-chat-user-step-id]')) return;
        const blocks = [...root.querySelectorAll('[data-block-id]')];
        const text = blocks.map(blockToMd).filter(l => l !== null && l !== '').join('\n');
        if (text) results.push({ role: 'assistant', text, node: root });
    });
    results.sort((a, b) => {
        const pos = a.node.compareDocumentPosition(b.node);
        if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
        if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
        return 0;
    });
    return results.map(({ role, text, id }) => ({ role, content: text, id }));
}
"""

# 取最後一則 assistant 回覆（chat() 返回值），含 Markdown 格式
_JS_GET_LAST_REPLY = r"""
() => {
    const roots = [...document.querySelectorAll('[data-content-editable-root="true"]')]
        .filter(r => !r.closest('[data-agent-chat-user-step-id]'));
    if (!roots.length) return null;
    const root = roots[roots.length - 1];

    function leafText(el) {
        // 收集葉節點文字，處理 inline 格式（bold/italic/code/strikethrough）
        let out = '';
        for (const node of el.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) {
                out += node.textContent;
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName;
                const inner = leafText(node);
                if (!inner) continue;
                if (tag === 'STRONG' || tag === 'B') out += `**${inner}**`;
                else if (tag === 'EM' || tag === 'I') out += `*${inner}*`;
                else if (tag === 'CODE') out += `\`${inner}\``;
                else if (tag === 'S' || tag === 'DEL') out += `~~${inner}~~`;
                else if (tag === 'A') {
                    const href = node.getAttribute('href') || '';
                    out += href ? `[${inner}](${href})` : inner;
                } else {
                    out += inner;
                }
            }
        }
        return out;
    }

    function blockToMd(block) {
        // 取 placeholder class 判斷 block 型別
        const cls = block.className || '';
        const leaf = block.querySelector('[data-content-editable-leaf="true"]');

        // code block（pre 或含 .notion-code-block class）
        const pre = block.querySelector('pre') || (block.tagName === 'PRE' ? block : null);
        if (pre) {
            // 嘗試抓語言標記
            const langEl = block.querySelector('[class*="language-"], [data-language]');
            const lang = langEl
                ? (langEl.getAttribute('data-language') || langEl.className.match(/language-(\S+)/)?.[1] || '')
                : '';
            return '```' + lang + '\n' + pre.textContent + '\n```';
        }

        if (!leaf) return null;

        const role = block.getAttribute('data-block-type')
            || block.getAttribute('aria-label')
            || '';

        // heading — Notion 用 placeholder text 或 data-block-type 標記
        // 偵測: 直接看字型大小 / 找 h1/h2/h3 標籤
        const hTag = block.querySelector('h1,h2,h3,h4,h5,h6');
        if (hTag) {
            const level = parseInt(hTag.tagName[1], 10);
            const text = leafText(leaf).trim();
            return '#'.repeat(level) + ' ' + text;
        }

        // bullet list item
        if (block.closest('[class*="bulleted"]') || cls.includes('bulleted')
            || block.querySelector('[class*="bulletedListItem"]')) {
            return '- ' + leafText(leaf).trim();
        }

        // numbered list item — 無法確定編號，統一用 1.
        if (block.closest('[class*="numbered"]') || cls.includes('numbered')
            || block.querySelector('[class*="numberedListItem"]')) {
            return '1. ' + leafText(leaf).trim();
        }

        // quote / callout — 用 > 前綴
        if (cls.includes('quote') || block.querySelector('[class*="quote"]')) {
            return '> ' + leafText(leaf).trim();
        }

        // 預設：paragraph
        return leafText(leaf).trim();
    }

    const blocks = [...root.querySelectorAll('[data-block-id]')];
    const lines = blocks.map(blockToMd).filter(l => l !== null && l !== '');
    return lines.join('\n') || null;
}
"""

# 點擊歷史面板中指定 react_id 的聊天室（同 _click_history_btn 的 dispatchEvent 模式）
_JS_CLICK_CHAT_ROOM = r"""
(reactId) => {
    const region = document.querySelector('[role="region"]');
    if (!region) return false;
    const items = [...region.querySelectorAll('[role="menuitem"]')]
        .filter(el => el.querySelector('svg.chatBubble'));
    for (const item of items) {
        if (item.id === reactId) {
            item.dispatchEvent(
                new MouseEvent('click', { bubbles: true, cancelable: true })
            );
            return true;
        }
    }
    return false;
}
"""

# 歷史面板是否已開：找 [role="region"] 底下的 <h2>Chat history</h2> 指紋
_JS_HISTORY_PANEL_OPEN = r"""
() => {
    const h2s = document.querySelectorAll('[role="region"] h2');
    for (const h of h2s) {
        const t = h.textContent.trim();
        if (t === 'Chat history' || t === '對話記錄' || t === '對話紀錄') return true;
    }
    return false;
}
"""


# ── Main class ─────────────────────────────────────────────────────────────────

class NotionAI:
    """Headless Playwright wrapper for Notion AI.

    Keeps the browser open for the object's lifetime — remember to call close()
    or use the `with` context manager.
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
        self._current_url: Optional[str]     = None

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
        self._pw  = sync_playwright().start()
        browser   = self._pw.chromium.launch(headless=self._headless)
        self._ctx = browser.new_context(storage_state=str(self._auth_path))
        self._page = self._ctx.new_page()
        print("[NotionAI] Chromium 已啟動", flush=True)

        self._page.goto(HOME_URL, wait_until="load")
        url = self._page.url
        # P13/P14: 檢查多種 redirect 路徑
        if any(seg in url for seg in ("/login", "/sign-up", "/select-workspace")):
            self.close()
            raise PermissionError(
                f"Notion session 已過期或未初始化（{url}），請重新執行 setup_auth.py"
            )
        self._log("Session 驗證成功")
        return self

    def close(self) -> None:
        """P15 修正：try/finally 確保 pw.stop() 一定執行。"""
        print("[NotionAI] 正在關閉 Chromium…", flush=True)
        try:
            if self._ctx:
                try:
                    self._ctx.close()
                except Exception as e:
                    self._log(f"Context close 失敗: {e}")
        finally:
            if self._pw:
                try:
                    self._pw.stop()
                except Exception as e:
                    self._log(f"Playwright stop 失敗: {e}")
            self._ctx = self._page = self._pw = None
            print("[NotionAI] Chromium 已關閉", flush=True)

    def __enter__(self) -> "NotionAI":
        return self.start()

    def __exit__(self, *_) -> None:
        self.close()

    # ── Public API ─────────────────────────────────────────────────────────────

    def list_chats(self) -> List[Dict[str, Any]]:
        """列出聊天室：[{'title', 'time', 'active', 'react_id'}, ...]"""
        page = self._assert_started()
        self._log("獲取聊天室列表…")
        try:
            self._ensure_ai_page()
            self._open_history_panel()
            # 等第一個 chatBubble menuitem 出現即可（各分組 spinner 永遠存在，不能用它判斷）
            try:
                page.wait_for_function(
                    """() => {
                        const region = document.querySelector('[role="region"]');
                        if (!region) return false;
                        return region.querySelector('[role="menuitem"] svg.chatBubble') !== null;
                    }""",
                    timeout=15_000,
                )
            except PWTimeout:
                pass
            return page.evaluate(_JS_LIST_CHATS)
        except Exception as e:
            self._log(f"獲取聊天室列表失敗: {e}")
            return []
        finally:
            try:
                self._close_history_panel()
            except Exception:
                pass

    def delete_chat(self, room: str) -> bool:
        """刪除指定聊天室，成功回傳 True，找不到回傳 False。

        room 可以是 URL / react_id / 聊天室標題（含字即可）。
        """
        page = self._assert_started()
        self._log(f"刪除聊天室: {room}")

        self._ensure_ai_page()
        self._open_history_panel()
        try:
            # 等聊天室列表載入
            try:
                page.wait_for_function(
                    """() => {
                        const region = document.querySelector('[role="region"]');
                        if (!region) return false;
                        return region.querySelector('[role="menuitem"] svg.chatBubble') !== null;
                    }""",
                    timeout=15_000,
                )
            except PWTimeout:
                pass

            chats = page.evaluate(_JS_LIST_CHATS)
            target = None

            if room.startswith("https://"):
                room_lower = room.lower()
                for c in chats:
                    if room_lower in (c.get("title") or "").lower():
                        target = c
                        break
            else:
                for c in chats:
                    if c.get("react_id") == room:
                        target = c
                        break
                if target is None:
                    for c in chats:
                        if c.get("title") == room:
                            target = c
                            break
                if target is None:
                    room_lower = room.lower()
                    for c in chats:
                        if room_lower in (c.get("title") or "").lower():
                            target = c
                            break

            if target is None:
                self._log(f'找不到聊天室 "{room}"')
                return False

            title = target["title"]
            self._log(f'找到聊天室: {title}')

            # Step 1: 用標題文字定位 item（不用 react_id，因為 react_id 在面板重開後會變）
            # 找含 chatBubble + 標題文字的 menuitem
            item_loc = page.locator('[role="region"] [role="menuitem"]').filter(
                has=page.locator('svg.chatBubble')
            ).filter(has_text=title).first
            try:
                item_loc.hover(timeout=8_000)
            except Exception as e:
                self._log(f'hover 失敗: {e}')
                return False
            page.wait_for_timeout(400)

            # Step 2: 等省略號按鈕出現，取座標後用 mouse.click()（JS click 觸發 app redirect）
            more_btn_loc = item_loc.locator(
                '[aria-label="刪除、重新命名等…"], [aria-label="More options"], [aria-label="Delete, rename, and more…"]'
            )
            try:
                more_btn_loc.wait_for(state="visible", timeout=3_000)
            except PWTimeout:
                self._log('省略號按鈕未出現')
                return False

            btn_rect = more_btn_loc.evaluate(
                """(btn) => {
                    const r = btn.getBoundingClientRect();
                    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                }"""
            )
            if not btn_rect:
                self._log('找不到省略號按鈕座標')
                return False
            page.mouse.click(btn_rect["x"], btn_rect["y"])

            # Step 3: 等省略號選單出現（role="menu" 不帶 aria-activedescendant 就是這個子選單）
            try:
                page.wait_for_selector(
                    '[role="menu"]:not([aria-activedescendant])',
                    timeout=5_000,
                )
            except PWTimeout:
                self._log("省略號選單未出現")
                return False

            # Step 4: 點「刪除」—— 找含 svg.trash 的 menuitem 並 dispatchEvent click
            deleted = page.evaluate(
                r"""() => {
                    const menu = document.querySelector('[role="menu"]:not([aria-activedescendant])');
                    if (!menu) return false;
                    const items = [...menu.querySelectorAll('[role="menuitem"]')];
                    for (const item of items) {
                        if (item.querySelector('svg.trash')) {
                            item.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                            return true;
                        }
                    }
                    return false;
                }"""
            )
            if not deleted:
                self._log("找不到「刪除」選項（svg.trash menuitem）")
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                return False

            # Step 5: 等確認 dialog 出現，點「確認」按鈕（class=notion-dialog-renderer-accept-item）
            try:
                page.wait_for_selector(
                    '.notion-dialog-renderer-accept-item',
                    timeout=5_000,
                )
            except PWTimeout:
                self._log("確認 dialog 未出現，可能已直接刪除")
            else:
                page.evaluate(
                    r"""() => {
                        const btn = document.querySelector('.notion-dialog-renderer-accept-item');
                        if (btn) btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    }"""
                )
                self._log("已點擊確認")

            # 等 UI 更新
            page.wait_for_timeout(800)
            self._log(f'聊天室已刪除: {target["title"]}')
            return True

        finally:
            try:
                self._close_history_panel()
            except Exception:
                pass

    def get_messages(self) -> List[Dict[str, str]]:
        """取當前聊天室的所有訊息：[{'role', 'content', 'id'?}, ...]

        需先透過 chat() 建立或進入某個聊天室。
        """
        page = self._assert_started()
        if not self._current_url:
            self._log("無活躍聊天室，無法取得訊息")
            return []
        if page.url != self._current_url:
            self._navigate(self._current_url)
        try:
            page.wait_for_function(
                """() => document.querySelectorAll(
                    '[data-agent-chat-user-step-id], [data-content-editable-root=\"true\"]'
                ).length > 0""",
                timeout=10_000,
            )
        except PWTimeout:
            pass
        messages = page.evaluate(_JS_GET_ALL_MESSAGES)
        self._log(f"獲取到 {len(messages)} 條訊息")
        return messages

    def chat(
        self,
        prompt:  str,
        *,
        model:   Optional[str] = None,
        timeout: int           = 30,
        room:    Optional[str] = None,
    ) -> Iterator[str]:
        """發送訊息並逐段串流回傳 AI 回覆。

        - `timeout`：發送後到出現**第一個 token** 的最大等待秒數（非總完成時間）。
        - `room`：指定目標聊天室，可傳 URL / react_id / 聊天室標題（含字即可）。
          省略時沿用現有路由邏輯（繼續/回到/新建）。
        - 回傳 Iterator[str]，逐段 yield 文字；完整文字可用 ``"".join(ai.chat(...))``。

        範例::

            for chunk in ai.chat("你好"):
                print(chunk, end="", flush=True)
        """
        page = self._assert_started()   # 立刻驗證，不懶惰（保持 TC-08b 行為）
        return self._chat_generator(page, prompt, model=model, timeout=timeout, room=room)

    def chat_sync(
        self,
        prompt:  str,
        *,
        model:   Optional[str] = None,
        timeout: int           = 30,
        room:    Optional[str] = None,
    ) -> str:
        """chat() 的非串流包裝，直接回傳完整回覆字串。"""
        return "".join(self.chat(prompt, model=model, timeout=timeout, room=room))

    def _chat_generator(
        self,
        page,
        prompt:  str,
        *,
        model:   Optional[str],
        timeout: int,
        room:    Optional[str],
    ) -> Iterator[str]:
        # A. 導航到目標聊天室
        if room is not None:
            self._click_chat_room(room)
        elif self._current_url and page.url == self._current_url:
            self._log("繼續當前聊天室")
        elif self._current_url:
            self._log(f"回到當前聊天室: {self._current_url}")
            self._navigate(self._current_url)
        else:
            self._log("建立新聊天室")
            self._create_new_conversation()

        # B. 設定模型
        if model:
            self._set_model(model)

        # C. 輸入並送出
        self._type_message(prompt)
        page.wait_for_function(
            f"""() => {{
                const b = document.querySelector('{SEL_SEND}');
                return b && b.getAttribute('aria-disabled') !== 'true';
            }}""",
            timeout=15_000,
        )
        page.click(SEL_SEND)

        # D. 等第一個 token（first-token timeout）
        try:
            page.wait_for_selector(SEL_STOP, state="visible", timeout=timeout * 1_000)
        except PWTimeout:
            raise TimeoutError(
                f"逾時 {timeout}s：AI 未回應（第一個 token 未出現）。"
            )

        # E. 更新 URL（第一次送出會從 /ai 跳到真實 chat URL）
        self._current_url = page.url

        # F. 串流迴圈
        last_text = ""
        while True:
            stop_visible = bool(page.query_selector(SEL_STOP))
            current = page.evaluate(_JS_GET_LAST_REPLY) or ""
            if current != last_text:
                yield current[len(last_text):]
                last_text = current
            if not stop_visible:
                # 防止 STOP 閃爍誤判：等 300ms 再確認一次
                page.wait_for_timeout(300)
                if not page.query_selector(SEL_STOP):
                    break
            else:
                page.wait_for_timeout(500)

        # G. 最後 drain（STOP 消失後可能還有殘餘文字）
        final = page.evaluate(_JS_GET_LAST_REPLY) or ""
        if final != last_text:
            yield final[len(last_text):]

    def get_models(self) -> List[Dict[str, Any]]:
        """返回可用模型清單：[{'name', 'selected', 'direct'}, ...]

        ``direct=False`` 為 Notion AI 路由版；``direct=True`` 為純語言模型直連。
        """
        page = self._assert_started()
        self._ensure_ai_page()
        try:
            self._click_model_button()
            page.wait_for_selector(SEL_MENU, timeout=10_000)
            # 等兩個 section 都載入（直連區為懶加載）
            try:
                page.wait_for_function(
                    f"() => document.querySelector('{SEL_MENU}')?.children.length >= 2",
                    timeout=5_000,
                )
            except PWTimeout:
                pass
            models = page.evaluate(_JS_MODEL_NAMES)
            page.keyboard.press("Escape")
            return models
        except Exception as e:
            self._log(f"獲取模型列表失敗: {e}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return []

    def current_model(self) -> Optional[str]:
        """直接讀左下角模型按鈕顯示的名稱（不展開選單）。"""
        page = self._assert_started()
        self._ensure_ai_page()
        return page.evaluate(_JS_CURRENT_MODEL)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _assert_started(self) -> Page:
        if not self._page:
            raise RuntimeError(
                "請先呼叫 start()，或使用 `with NotionAI(...) as ai:` 語法。"
            )
        return self._page

    def _ensure_ai_page(self) -> None:
        """確保當前頁是 /ai（有輸入框）。"""
        page = self._page
        if "notion.so/ai" not in page.url:
            page.goto(AI_URL, wait_until="load")
            page.wait_for_selector(f"{SEL_INPUT}, {SEL_INPUT_F}", timeout=15_000)

    def _navigate(self, url: str) -> None:
        self._log(f"導航到: {url}")
        self._page.goto(url, wait_until="load")
        self._page.wait_for_selector(f"{SEL_INPUT}, {SEL_INPUT_F}", timeout=15_000)

    def _create_new_conversation(self) -> None:
        """P24 修正：直接 goto /ai 即可開新對話，不需 Start new chat 按鈕。"""
        page = self._page
        page.goto(AI_URL, wait_until="load")
        page.wait_for_selector(f"{SEL_INPUT}, {SEL_INPUT_F}", timeout=15_000)
        self._current_url = page.url
        self._log(f"新聊天室已建立: {self._current_url}")

    # ── 歷史面板（冪等，P3 修正）───────────────────────────────────────────────

    def _is_history_panel_open(self) -> bool:
        return bool(self._page.evaluate(_JS_HISTORY_PANEL_OPEN))

    def _click_history_btn(self) -> None:
        """用 JS dispatchEvent 繞過 <h2> 遮罩觸發歷史面板按鈕。"""
        self._page.evaluate(
            f"""() => {{
                const btn = document.querySelector('{SEL_HISTORY_BTN}');
                if (btn) btn.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
            }}"""
        )

    def _open_history_panel(self) -> None:
        page = self._page
        if self._is_history_panel_open():
            return
        self._click_history_btn()
        page.wait_for_function(_JS_HISTORY_PANEL_OPEN, timeout=15_000)

    def _close_history_panel(self) -> None:
        page = self._page
        if not self._is_history_panel_open():
            return
        try:
            self._click_history_btn()
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

    def _click_chat_room(self, room: str) -> None:
        """導航到指定聊天室。

        room 可以是：
          - URL（startswith "https://"）→ 直接導航
          - react_id（如 ":r1h:"）→ 從歷史面板精確匹配
          - 聊天室標題 → 先精確匹配，再 contains 匹配（大小寫不敏感）
        """
        page = self._page

        if room.startswith("https://"):
            self._navigate(room)
            self._current_url = page.url
            return

        self._ensure_ai_page()
        self._open_history_panel()
        try:
            # 等聊天室列表載入
            try:
                page.wait_for_function(
                    """() => {
                        const region = document.querySelector('[role="region"]');
                        if (!region) return false;
                        return region.querySelector('[role="menuitem"] svg.chatBubble') !== null;
                    }""",
                    timeout=15_000,
                )
            except PWTimeout:
                pass

            chats = page.evaluate(_JS_LIST_CHATS)
            target = None

            # 1. exact react_id
            for c in chats:
                if c.get("react_id") == room:
                    target = c
                    break

            # 2. exact title
            if target is None:
                for c in chats:
                    if c.get("title") == room:
                        target = c
                        break

            # 3. contains title（大小寫不敏感）
            if target is None:
                room_lower = room.lower()
                for c in chats:
                    if room_lower in (c.get("title") or "").lower():
                        target = c
                        break

            if target is None:
                raise ValueError(
                    f'找不到聊天室 "{room}"。'
                    f'可用標題（前 5 筆）: {[c["title"] for c in chats[:5]]}'
                )

            react_id = target["react_id"]
            clicked = page.evaluate(_JS_CLICK_CHAT_ROOM, react_id)
            if not clicked:
                raise RuntimeError(f'無法點擊聊天室 react_id="{react_id}"')

            page.wait_for_selector(f"{SEL_INPUT}, {SEL_INPUT_F}", timeout=15_000)
            self._current_url = page.url
        finally:
            try:
                self._close_history_panel()
            except Exception:
                pass

    # ── 輸入 / 等待 ────────────────────────────────────────────────────────────

    def _type_message(self, text: str) -> None:
        """P10 修正：改用 Playwright 原生 click + keyboard.type，
        確保觸發 React 合成 InputEvent，Send 按鈕才會解除 disabled。
        """
        page = self._page
        editor = page.locator(f"{SEL_INPUT}, {SEL_INPUT_F}").first
        editor.click()
        mod = "Meta" if sys.platform == "darwin" else "Control"
        page.keyboard.press(f"{mod}+A")
        page.keyboard.press("Delete")
        page.keyboard.type(text, delay=0)

    def _wait_for_reply_complete(self, timeout_ms: int = 90_000) -> None:
        """等 STOP 按鈕出現後再等它消失（不再被 chat() 呼叫，保留供外部使用）。"""
        page = self._page
        try:
            page.wait_for_selector(SEL_STOP, state="visible", timeout=3_000)
        except PWTimeout:
            pass
        try:
            page.wait_for_selector(SEL_STOP, state="hidden", timeout=timeout_ms)
        except PWTimeout:
            pass

    def _get_last_reply(self) -> Optional[str]:
        return self._page.evaluate(_JS_GET_LAST_REPLY)

    # ── 模型切換（P4 修正）─────────────────────────────────────────────────────

    def _click_model_button(self) -> None:
        """用 JS dispatchEvent 繞過 role=presentation 遮罩層直接觸發模型按鈕。"""
        self._page.evaluate(
            f"""() => {{
                const btn = document.querySelector('{SEL_MODEL}');
                if (btn) btn.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
            }}"""
        )

    def _set_model(self, model_name: str) -> None:
        """切換模型。

        model_name 格式：
          - ``"Sonnet 4.6"``          → 第一區（Notion AI 路由版）
          - ``"direct:Sonnet 4.6"``   → 第二區（純語言模型直連）
        """
        page = self._page
        self._ensure_ai_page()

        direct = model_name.startswith("direct:")
        bare_name = model_name[len("direct:"):] if direct else model_name

        # 若當前模型已是目標，直接跳過
        if page.evaluate(_JS_CURRENT_MODEL) == bare_name:
            return

        # 預先驗證：必須在可用模型清單裡（且 direct 符合）
        models = self.get_models()
        matching = [m for m in models if m["name"] == bare_name and m["direct"] == direct]
        if not matching:
            all_names = [f"direct:{m['name']}" if m["direct"] else m["name"] for m in models]
            raise ValueError(
                f'找不到 model "{model_name}"。可用: {all_names}'
            )

        # 打開選單並點擊對應項
        self._click_model_button()
        page.wait_for_selector(SEL_MENU, timeout=10_000)
        clicked = page.evaluate(_JS_CLICK_MODEL_ITEM, [bare_name, direct])
        if not clicked:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            raise RuntimeError(f'模型選單中找不到項目 "{model_name}"')


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "用一句話打個招呼。"
    print(f"Prompt: {prompt}")

    with NotionAI(debug=True) as ai:
        print("Reply : ", end="", flush=True)
        for chunk in ai.chat(prompt=prompt):
            print(chunk, end="", flush=True)
        print()

        if not sys.argv[1:]:
            print("\n=== 多輪對話測試 ===")
            r1 = ai.chat_sync(prompt="請記住數字 42，回覆「已記住」")
            print(f"輪次 1: {r1}")
            r2 = ai.chat_sync(prompt="我剛才請你記住什麼數字？")
            print(f"輪次 2: {r2}")

            print("\n=== 訊息歷史 ===")
            for m in ai.get_messages():
                head = (m['content'] or '').replace('\n', ' ')[:80]
                print(f"[{m['role']}] {head}")