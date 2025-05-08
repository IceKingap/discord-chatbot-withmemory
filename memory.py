# memory.py — OpenAI v1.x + 短期メモリ + System指示初期登録 + 重複抑止 + 自動次元チェック
import os, datetime, sqlite3, logging
from typing import List, Dict
import chromadb
from chromadb.errors import InvalidDimensionException   # ★
from openai import OpenAI

# ---------- 追加指示 ---------------------------------------------------------------
CHAT_INSTR = (
    "あなたはこのサーバーのAIメンバーです。言われたことを従順に守ってください。"
    "必要な時のみ長文にし、それ以外は短い文で出力してください。"
)
TASK_INSTR = (
    "これは AI 側から自発的に話しかけるメッセージです。長い時間が経った後だと思って、違う話題を出してください。"
    "必要な時のみ長文にし、それ以外は短い文で出力してください。"
)
SYSTEM_MSG = CHAT_INSTR  # ID=0 / sys‑0 で常駐させる

logging.getLogger("chromadb").setLevel(logging.WARNING)

# ---------- フォルダ ---------------------------------------------------------------
os.makedirs("db", exist_ok=True)

# ---------- SQLite -----------------------------------------------------------------
con = sqlite3.connect("db/history.db")
con.execute(
    """
    CREATE TABLE IF NOT EXISTS msgs(
        id INTEGER PRIMARY KEY,
        user TEXT, role TEXT, content TEXT, ts TEXT
    )
    """
)

# ---------- Chroma 初期化 ----------------------------------------------------------
client_vec = chromadb.PersistentClient(path="chroma")
col = client_vec.get_or_create_collection("memory")

# ---------- OpenAI -----------------------------------------------------------------
client_oa = OpenAI()

# ---------- 埋め込み関数 -----------------------------------------------------------
EMBED_MODEL = "text-embedding-3-large"        # ★ ここを書き換えるだけで OK
def embed(text: str) -> List[float]:
    return client_oa.embeddings.create(
        model=EMBED_MODEL,
        input=text,
    ).data[0].embedding

# ---------- ★ コレクションと埋め込み次元を自動整合 -------------------------------
def _ensure_collection_dimension():
    test_id = "_dim_test_"
    test_emb = embed("dimension-test")
    try:
        # 試しに追加してみる → 成功すれば次元は合っている
        col.add(ids=[test_id], embeddings=[test_emb],
                documents=["dim"], metadatas=[{"user": "system"}])
        col.delete(ids=[test_id])
    except InvalidDimensionException:
        # 次元不一致 → コレクションを削除して再生成
        client_vec.delete_collection("memory")
        globals()["col"] = client_vec.get_or_create_collection("memory")
        # もう一度追加・削除で確認
        col.add(ids=[test_id], embeddings=[test_emb],
                documents=["dim"], metadatas=[{"user": "system"}])
        col.delete(ids=[test_id])

_ensure_collection_dimension()    # ★ ここを最初に呼ぶ

# ---------- System 指示を 1 回だけ登録 --------------------------------------------
def _ensure_system_memory():
    if not con.execute("SELECT 1 FROM msgs WHERE id=0").fetchone():
        con.execute(
            "INSERT INTO msgs(id,user,role,content,ts) VALUES(0,'system','system',?,?)",
            (SYSTEM_MSG, datetime.datetime.utcnow().isoformat()),
        )
        con.commit()
    if "sys-0" not in col.get()["ids"]:
        col.add(
            ids=["sys-0"],
            embeddings=[embed(SYSTEM_MSG)],
            documents=[SYSTEM_MSG],
            metadatas=[{"user": "system"}],
        )

_ensure_system_memory()

# ---------- store / add_memory -----------------------------------------------------
def store(msg):
    if getattr(msg.author, "bot", False):
        return
    con.execute(
        "INSERT INTO msgs VALUES(NULL,?,?,?,?)",
        (getattr(msg.author, "id", "system"), "user",
         msg.content, datetime.datetime.utcnow().isoformat()),
    )
    con.commit()

def add_memory(msg):
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
def _fetch_recent(limit=6) -> List[Dict[str, str]]:
    rows = reversed(
        con.execute("SELECT role,content FROM msgs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    )
    return [{"role": r, "content": c} for r, c in rows]

def build_prompt(latest_q: str | None = None) -> List[Dict[str, str]]:
    memories_block = ""
    if col.count():
        docs = col.query(query_embeddings=[embed(latest_q or "hello")],
                         n_results=min(4, col.count()))
        memories_block = "\n".join(docs["documents"][0]) if docs["documents"] else ""
    prompt: List[Dict[str, str]] = []
    if memories_block:
        prompt.append({"role": "assistant", "content": memories_block})
    prompt.extend(_fetch_recent())
    if latest_q is not None:
        prompt.append({"role": "user", "content": latest_q})
    return prompt

# ---------- 完全リセット -----------------------------------------------------------
def reset_all_memory():
    con.execute("DELETE FROM msgs")
    con.commit()
    client_vec.delete_collection("memory")
    globals()["col"] = client_vec.get_or_create_collection("memory")
    _ensure_collection_dimension()   # ★ 新しいモデル次元で再整合
    _ensure_system_memory()          # System 指示を復元
