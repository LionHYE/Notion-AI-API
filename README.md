# Notion AI API

A headless Playwright wrapper that lets you interact with [Notion AI](https://www.notion.so/product/ai) programmatically — no official API required.

## Features

- **Streaming responses** — get AI responses in real-time chunks
- **Single-turn chat** — send a prompt and get a reply
- **Multi-turn conversation** — continue the same chat across multiple calls
- **Switch conversations** — resume any existing chat by URL, react_id, or title
- **List chats** — retrieve the conversation history sidebar
- **Delete chats** — remove conversations programmatically
- **Fetch messages** — read all messages in a given conversation
- **Model selection** — switch between available Notion AI models at runtime
- **Markdown formatting** — responses preserve Notion's formatting in Markdown

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

### Streaming responses (recommended)

```python
from notion_ai import NotionAI

with NotionAI(debug=True) as ai:
    # Stream response chunks (like ChatGPT typing effect)
    for chunk in ai.chat(prompt="Summarize my notes in one paragraph."):
        print(chunk, end="", flush=True)
```

### Non-streaming responses

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    # Get complete response as a single string
    reply = ai.chat_sync(prompt="Summarize my notes in one paragraph.")
    # Or equivalently: reply = "".join(ai.chat(prompt="..."))
    print(reply)
```

### Multi-turn conversation

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    ai.chat_sync(prompt="My name is Alex.")
    reply = ai.chat_sync(prompt="What is my name?")  # continues the same chat
    print(reply)
```

### Specify or switch conversations

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    # Start in a specific conversation (URL, react_id, or title)
    reply = ai.chat_sync(prompt="Hello", room="https://www.notion.so/ai/<id>")
    # Or by title (partial match works too)
    reply = ai.chat_sync(prompt="Hello", room="My Chat Title")

    # Continue that conversation (no `room` arg needed afterwards)
    reply = ai.chat_sync(prompt="Follow-up question")
    
    # Get all messages in the current conversation
    messages = ai.get_messages()
```

### Select a model

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    # List available models
    models = ai.get_models()
    print(models)
    
    # Use a specific model
    reply = ai.chat_sync(prompt="Hello", model="Opus 4.7")
    
    # Use direct model access (bypassing Notion AI routing)
    reply = ai.chat_sync(prompt="Hello", model="direct:Sonnet 4.6")
    
    # Check current model
    current = ai.current_model()
    print(f"Currently using: {current}")
```

### Delete conversations

```python
from notion_ai import NotionAI

with NotionAI() as ai:
    # List all chats
    chats = ai.list_chats()
    
    # Delete a chat by title (partial match works)
    success = ai.delete_chat("My Chat Title")
    
    # Or by URL
    success = ai.delete_chat("https://www.notion.so/ai/<id>")
    
    # Or by react_id
    success = ai.delete_chat(":r1h:")
```

### Manual lifecycle

```python
from notion_ai import NotionAI

ai = NotionAI(debug=True)
ai.start()

chats = ai.list_chats()
messages = ai.get_messages()
reply = ai.chat_sync(prompt="Hello")

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
| `chat(prompt, *, model, timeout, room)` | `Iterator[str]` | Stream AI response chunks |
| `chat_sync(prompt, *, model, timeout, room)` | `str` | Send a message and return the complete AI reply |
| `list_chats()` | `List[Dict]` | List conversations from the history sidebar |
| `delete_chat(room)` | `bool` | Delete a conversation by URL, react_id, or title |
| `get_messages()` | `List[Dict]` | Fetch all messages in the current conversation |
| `get_models()` | `List[Dict]` | List available AI models |
| `current_model()` | `Optional[str]` | Get the name of the currently selected model |

## Security Notice

`notion_auth.json` contains your Notion session token. It is listed in `.gitignore` and should **never** be committed or shared.

## License

MIT