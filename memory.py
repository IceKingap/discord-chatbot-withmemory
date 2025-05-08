# memory.py — OpenAI v1.x + 短期メモリ + System指示初期登録 + 重複抑止
import os, datetime, sqlite3, logging
from typing import List, Dict
import chromadb
from openai import OpenAI

# ---------- 追加指示 ---------------------------------------------------------------
CHAT_INSTR = (
    "あなたはこのサーバーのAIメンバーですが、名前は拓也、サーフ系ボディービルダーでガタイが良く、ボーイッシュなしゃべり方をしてください。セリフ例：「ウッス！」「ヤッス！」「ハメられた！」「～だぜ」「マジやべー。」「わかんねぇ。」「信じらんねぇ！」"
    "必要な時のみ長文にし、それ以外は短い文で出力してください。"
)

# ★ 修正: TASK_INSTR の文字列を正しく閉じ、1 行にまとめる
TASK_INSTR = (
    "これは AI 側から自発的に話しかけるメッセージです。長い時間が経った後だと思って、違う話題を出してください。"
    "必要な時のみ長文にし、それ以外は短い文で出力してください。"
)

SYSTEM_MSG = CHAT_INSTR  # 最初に SQLite / Chroma へ 1 回だけ登録する固定文

logging.getLogger("chromadb").setLevel(logging.WARNING)

# ---------- 永続フォルダ -----------------------------------------------------------
os.makedirs("db", exist_ok=True)

# ---------- SQLite -----------------------------------------------------------------
con = sqlite3.connect("db/history.db")
con.execute(
    """
    CREATE TABLE IF NOT EXISTS msgs (
        id      INTEGER PRIMARY KEY,
        user    TEXT,
        role    TEXT,
        content TEXT,
        ts      TEXT
    )
    """
)

# ---------- Chroma -----------------------------------------------------------------
client_vec = chromadb.PersistentClient(path="chroma")
col = client_vec.get_or_create_collection("memory")

# ---------- OpenAI -----------------------------------------------------------------
client_oa = OpenAI()  # OPENAI_API_KEY は環境変数から自動読込

# ---------- 埋め込み ----------------------------------------------------------------
def embed(text: str) -> List[float]:
    return client_oa.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    ).data[0].embedding

# ---------- System 指示を 1 回だけ登録 ---------------------------------------------
def _ensure_system_memory():
    # SQLite に ID=0 が無ければ挿入
    if not con.execute("SELECT 1 FROM msgs WHERE id=0").fetchone():
        con.execute(
            "INSERT INTO msgs(id,user,role,content,ts) VALUES(0,'system','system',?,?)",
            (SYSTEM_MSG, datetime.datetime.utcnow().isoformat()),
        )
        con.commit()

    # Chroma に sys‑0 が無ければ追加
    if col.count() == 0 or "sys-0" not in col.get()["ids"]:
        col.add(
            ids=["sys-0"],
            embeddings=[embed(SYSTEM_MSG)],
            documents=[SYSTEM_MSG],
            metadatas=[{"user": "system"}],
        )

_ensure_system_memory()

# ---------- store / add_memory ------------------------------------------------------
def store(msg):
    """SQLite 保存（Bot 自己発話は除外）"""
    if getattr(msg.author, "bot", False):
        return
    con.execute(
        "INSERT INTO msgs VALUES(NULL,?,?,?,?)",
        (
            getattr(msg.author, "id", "system"),
            "user",
            msg.content,
            datetime.datetime.utcnow().isoformat(),
        ),
    )
    con.commit()

def add_memory(msg):
    """Chroma 保存（Bot 自己発話は除外、ID 重複はスキップ）"""
    if getattr(msg.author, "bot", False):
        return
    msg_id = str(getattr(msg, "id", datetime.datetime.utcnow().timestamp()))
    if col.count() and msg_id in col.get(ids=[msg_id]).get("ids", []):
        return
    col.add(
        ids=[msg_id],
        embeddings=[embed(msg.content)],
        documents=[msg.content],
        metadatas=[{"user": str(getattr(msg.author, "id", "system"))}],
    )

# ---------- プロンプト生成 -----------------------------------------------------------
def _fetch_recent(limit: int = 6) -> List[Dict[str, str]]:
    rows = reversed(
        con.execute(
            "SELECT role, content FROM msgs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    )
    return [{"role": r, "content": c} for r, c in rows]

def build_prompt(latest_q: str | None = None) -> List[Dict[str, str]]:
    """類似記憶 + 直近会話 + 最新ユーザ入力"""
    memories_block = ""
    if col.count():
        docs = col.query(
            query_embeddings=[embed(latest_q or "hello")],
            n_results=min(4, col.count()),
        )
        memories_block = "\n".join(docs["documents"][0]) if docs["documents"] else ""

    prompt: List[Dict[str, str]] = []
    if memories_block:
        prompt.append({"role": "assistant", "content": memories_block})
    prompt.extend(_fetch_recent())
    if latest_q is not None:
        prompt.append({"role": "user", "content": latest_q})
    return prompt

# ---------- 完全リセット ------------------------------------------------------------
def reset_all_memory():
    """SQLite と Chroma を空にしたあと、System 指示を再登録"""
    con.execute("DELETE FROM msgs")
    con.commit()
    client_vec.delete_collection("memory")
    globals()["col"] = client_vec.get_or_create_collection("memory")
    _ensure_system_memory()  # System 指示を復元
