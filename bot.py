import os
import time
from types import SimpleNamespace

import discord
import dotenv
from discord.ext import commands, tasks
from openai import OpenAI

# ── ❶ .env 読み込み ───────────────────────────────
dotenv.load_dotenv()

# ── ❷ OpenAI v1 クライアント ─────────────────────
client_oa = OpenAI()

# ── ❸ memory モジュール ──────────────────────────
from memory import (
    store,
    add_memory,
    build_prompt,
    reset_all_memory,
    CHAT_INSTR,   # 会話用システム指示
    TASK_INSTR,   # 定期タスク用システム指示
)

# ── ❹ Discord Bot オブジェクト ────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ── ❺ 自動送信タスク (10 時間ごと) ───────────────────
channel_id = int(os.getenv("CHANNEL_ID", 0))

@tasks.loop(hours=10)
async def hourly():
    ch = bot.get_channel(channel_id)
    if not ch:
        return

    messages = build_prompt() + [{"role": "system", "content": TASK_INSTR}]

    chat = client_oa.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        max_tokens=100,
    )
    ans = chat.choices[0].message.content
    await ch.send(ans)

    # Bot の発話もメモリへ保存
    dummy = SimpleNamespace(id=int(time.time() * 1000), author=bot.user, content=ans)
    store(dummy)
    add_memory(dummy)

# ── ❻ Discord イベント ────────────────────────────
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not hourly.is_running():
        hourly.start()

@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    # ★変更: すべてのユーザーメッセージを記憶
    store(msg)
    add_memory(msg)

    await bot.process_commands(msg)

# ── ❼ !ask コマンド ───────────────────────────────
@bot.command()
async def ask(ctx, *, q: str):
    messages = [{"role": "system", "content": CHAT_INSTR}] + build_prompt(q)

    chat = client_oa.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        max_tokens=1000,
    )
    ans = chat.choices[0].message.content
    await ctx.send(ans)

    # Bot の返答を保存
    dummy = SimpleNamespace(id=ctx.message.id, author=bot.user, content=ans)
    store(dummy)
    add_memory(dummy)

# ── ❽ 管理者専用：記憶リセット ───────────────────
@bot.command()
@commands.is_owner()
async def reset_mem(ctx):
    reset_all_memory()
    await ctx.send("🗑️ 記憶をリセットしました")

# ── ❾ 起動 ────────────────────────────────────────
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
