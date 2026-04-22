# Notion AI API

A headless Playwright wrapper that lets you interact with [Notion AI](https://www.notion.so/product/ai) programmatically — no official API required.

## Features

- **Single-turn chat** — send a prompt and get a reply
- **Multi-turn conversation** — continue the same chat across multiple calls
- **Switch conversations** — resume any existing chat by URL
- **List chats** — retrieve the conversation history sidebar
- **Fetch messages** — read all messages in a given conversation
- **Model selection** — switch between available Notion AI models at runtime

## Requirements

- Python 3.9+
- A Notion account with AI access

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Setup (one-time)

Run the following command to save your Notion session locally. A browser window will open — log in to Notion, then press Enter in the terminal.

```bash
python setup_auth.py
```

This creates `notion_auth.json` in the project root. **Do not commit this file** — it contains your session token.

## Usage

### Context manager (recommended)

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    reply = ai.chat(prompt="Summarise my notes in one paragraph.")
    print(reply)
```

### Multi-turn conversation

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    ai.chat(prompt="My name is Alex.")
    reply = ai.chat(prompt="What is my name?")  # continues the same chat
    print(reply)
```

### Specify or switch conversations

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    # Start in a specific conversation
    reply = ai.chat(prompt="Hello", chat="https://www.notion.so/ai/<id>")

    # Continue that conversation (no `chat` arg needed afterwards)
    reply = ai.chat(prompt="Follow-up question")
```

### Select a model

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    reply = ai.chat(prompt="Hello", model="Opus 4.7")
```

### Manual lifecycle

```python
from notion_ai import NotionAI

ai = NotionAI(debug=True)
ai.start()

chats = ai.list_chats()
messages = ai.get_messages("https://www.notion.so/ai/<id>")
reply = ai.chat(prompt="Hello")

ai.close()
```

## API Reference

### `NotionAI(auth_path, headless, debug)`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `auth_path` | `str \| Path` | `"notion_auth.json"` | Path to the saved session file |
| `headless` | `bool` | `True` | Run browser in headless mode |
| `debug` | `bool` | `False` | Print debug logs |

### Methods

| Method | Returns | Description |
|---|---|---|
| `start()` | `NotionAI` | Launch the browser and verify the session |
| `close()` | `None` | Close the browser |
| `chat(prompt, *, chat, model, timeout)` | `str` | Send a message and return the AI reply |
| `list_chats()` | `list[dict]` | List conversations from the history sidebar |
| `get_messages(chat)` | `list[dict]` | Fetch all messages in a conversation |
| `get_models()` | `list[dict]` | List available AI models |

## Security Notice

`notion_auth.json` contains your Notion session token. It is listed in `.gitignore` and should **never** be committed or shared.

## License

MIT
