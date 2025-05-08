# discord-chatbot-withmemory
Chatbot with memory functionality and periodic spontaneous messages via vector conversion
# Discord Memory Bot 🧠

A small Discord bot that

* answers `!ask` questions with **OpenAI GPT‑4.1** (or any model you prefer)  
* remembers conversations in **SQLite + Chroma** (short‑ & long‑term memory)  
* sends a friendly “ice‑breaker” message every *N* minutes (fully configurable)  
* keeps a single, permanent **System prompt** in memory so the bot never “forgets its personality”  
* resets its entire memory with `!reset_mem` (owner only)
 
> Tune `CHAT_INSTR` and `TASK_INSTR` in `memory.py` to anything you like.

---

# · Prerequisites

|           | Version |
|-----------|---------|
| Python    | **3.11 64‑bit** (3.12+ works but wheel availability may vary) |
| Discord   | A bot application with **MESSAGE CONTENT Intent** enabled |
| OpenAI API| A key with access to the models you plan to use |

---

.envファイルにAPIキー、discordbotトークン、discordチャンネルidを入力してください。
各依存関係をインストール（chatGPTに聞いてください）し、bot.pyを実行すれば動きます。
Logged in as (bot name)と出れば成功です。

ファイルはすべて同じ階層でOKです。
