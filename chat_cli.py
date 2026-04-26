"""
Notion AI — 互動式終端機聊天
執行: python chat_cli.py
"""
from __future__ import annotations

import sys
from notion_ai import NotionAI


def main():
    print("=== Notion AI 終端機聊天 ===")
    print("輸入訊息後按 Enter 送出，輸入 /quit 或 Ctrl+C 離開\n")

    headless = "--show" not in sys.argv
    model = None
    for arg in sys.argv[1:]:
        if arg.startswith("--model="):
            model = arg.split("=", 1)[1]

    ai = NotionAI(headless=headless, debug=False)
    ai.start()
    print(f"瀏覽器已啟動。{'（背景執行）' if headless else '（視窗模式）'}")
    if model:
        print(f"模型: {model}")
    print()

    try:
        while True:
            try:
                user_input = input("你: ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "/q"):
                break

            print("AI: ", end="", flush=True)
            try:
                for chunk in ai.chat(prompt=user_input, model=model, timeout=60):
                    print(chunk, end="", flush=True)
                print()
            except TimeoutError:
                print("\n[逾時：AI 未在 60 秒內回應]")
            except Exception as e:
                print(f"\n[錯誤: {e}]")
            print()

    except KeyboardInterrupt:
        print("\n\n離開中…")
    finally:
        ai.close()


if __name__ == "__main__":
    main()
