"""2026-11-10 新写的本地演示：审批、幂等和丢响应后的恢复。仅用合成数据。"""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid


class SimulatedTimeout(TimeoutError):
    """接收端已提交回执，但调用方没有收到响应。"""


class Workflow:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, prompt_version TEXT NOT NULL,
                state TEXT NOT NULL, approved_hash TEXT, reviewer TEXT);
            CREATE TABLE IF NOT EXISTS operations (
                key TEXT PRIMARY KEY, document_id TEXT UNIQUE NOT NULL,
                payload_hash TEXT NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts (
                key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
                receipt_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receiver_calls (
                key TEXT PRIMARY KEY, calls INTEGER NOT NULL);
        """)

    def close(self):
        self.db.close()

    def document(self, document_id):
        row = self.db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise KeyError(document_id)
        return row

    @staticmethod
    def payload(row):
        data = {key: row[key] for key in ("id", "content", "prompt_version")}
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def draft(self, document_id, content, prompt_version="v1"):
        with self.db:
            self.db.execute("INSERT INTO documents VALUES (?, ?, ?, 'draft', NULL, NULL)",
                            (document_id, content, prompt_version))

    def revise(self, document_id, *, content=None, prompt_version=None):
        with self.db:
            row = self.document(document_id)
            if self.db.execute("SELECT 1 FROM operations WHERE document_id=?",
                               (document_id,)).fetchone():
                raise ValueError("发送意图已持久化，保留历史；修改请创建新文档。")
            self.db.execute("""UPDATE documents SET content=?, prompt_version=?,
                            state='draft', approved_hash=NULL, reviewer=NULL WHERE id=?""",
                            (row["content"] if content is None else content,
                             row["prompt_version"] if prompt_version is None else prompt_version,
                             document_id))

    def review(self, document_id):
        with self.db:
            result = self.db.execute("UPDATE documents SET state='reviewed' WHERE id=? AND state='draft'",
                                     (document_id,))
            if result.rowcount != 1:
                raise ValueError("只有 draft 可以进入 reviewed。")

    def approve(self, document_id, reviewer):
        # 演示由调用方显式提供审批；这里没有真实身份认证系统。
        if not reviewer.strip():
            raise PermissionError("必须记录模拟审批人。")
        with self.db:
            row = self.document(document_id)
            if row["state"] != "reviewed":
                raise ValueError("只有 reviewed 可以审批。")
            _, digest = self.payload(row)
            self.db.execute("""UPDATE documents SET state='approved', approved_hash=?,
                            reviewer=? WHERE id=?""", (digest, reviewer, document_id))

    def receipt(self, key, digest):
        row = self.db.execute("SELECT * FROM receipts WHERE key=?", (key,)).fetchone()
        if row is not None and row["payload_hash"] != digest:
            raise ValueError("幂等键与既有接收端 payload 冲突。")
        return row

    def _receiver_submit(self, key, digest, payload):
        # 独立事务模拟接收端：没有任何网络、邮箱或发布平台调用。
        with self.db:
            self.db.execute("""INSERT INTO receiver_calls VALUES (?, 1)
                            ON CONFLICT(key) DO UPDATE SET calls=calls+1""", (key,))
            row = self.receipt(key, digest)
            if row is None:
                self.db.execute("INSERT INTO receipts VALUES (?, ?, ?, ?)",
                                (key, digest, "local-" + uuid.uuid4().hex[:12], payload))
        return self.receipt(key, digest)

    def send(self, document_id, key, *, lose_response=False):
        with self.db:
            row = self.document(document_id)
            payload, digest = self.payload(row)
            if row["state"] not in ("approved", "simulated_sent") or row["approved_hash"] != digest:
                raise PermissionError("当前正文与提示版本没有有效审批。")
            op = self.db.execute("SELECT * FROM operations WHERE key=?", (key,)).fetchone()
            if op and (op["document_id"] != document_id or op["payload_hash"] != digest):
                raise ValueError("同一幂等键不能用于另一份 payload。")
            existing = self.db.execute("SELECT key FROM operations WHERE document_id=?",
                                       (document_id,)).fetchone()
            if existing and existing["key"] != key:
                raise ValueError("同一文档必须复用已持久化的幂等键。")
            self.db.execute("INSERT OR IGNORE INTO operations VALUES (?, ?, ?, 'pending')",
                            (key, document_id, digest))
        # 操作先持久化；每次恢复先查询回执，查到即不再次调用接收端。
        receipt = self.receipt(key, digest)
        if receipt is None:
            receipt = self._receiver_submit(key, digest, payload)
            if lose_response:
                raise SimulatedTimeout("回执已落库，模拟响应丢失；保持 pending。")
        with self.db:
            self.db.execute("UPDATE operations SET status='confirmed' WHERE key=?", (key,))
            self.db.execute("UPDATE documents SET state='simulated_sent' WHERE id=?", (document_id,))
        return receipt["receipt_id"]


def expect_error(error_type, action):
    try:
        action()
    except error_type:
        return
    raise AssertionError("未触发预期异常：" + error_type.__name__)


def prepare(app, document_id, content):
    app.draft(document_id, content)
    app.review(document_id)
    app.approve(document_id, "synthetic-reviewer")


def self_check(database):
    app = Workflow(database)
    app.draft("approval", "合成文稿 A")
    expect_error(PermissionError, lambda: app.send("approval", "key-a"))
    print("PASS unapproved send rejected")
    app.review("approval")
    app.approve("approval", "synthetic-reviewer")
    app.revise("approval", content="合成文稿 A 修订")
    expect_error(PermissionError, lambda: app.send("approval", "key-a"))
    assert app.document("approval")["approved_hash"] is None
    print("PASS content edit invalidates approval")
    app.review("approval")
    app.approve("approval", "synthetic-reviewer")
    app.revise("approval", prompt_version="v2")
    expect_error(PermissionError, lambda: app.send("approval", "key-a"))
    print("PASS prompt version edit invalidates approval")
    prepare(app, "timeout", "合成文稿 B：仅在本地模拟发送。")
    expect_error(SimulatedTimeout, lambda: app.send("timeout", "key-timeout", lose_response=True))
    receipt_id = app.db.execute("SELECT receipt_id FROM receipts WHERE key='key-timeout'").fetchone()[0]
    assert app.db.execute("SELECT status FROM operations WHERE key='key-timeout'").fetchone()[0] == "pending"
    assert app.document("timeout")["state"] == "approved"
    app.close()
    # 真正启动第二个 Python 进程，复用同一个已提交到磁盘的 SQLite 文件。
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                             "--resume-self-check", str(database)], check=True,
                            capture_output=True, text=True, encoding="utf-8")
    assert json.loads(result.stdout)["receipt_id"] == receipt_id
    app = Workflow(database)
    assert app.document("timeout")["state"] == "simulated_sent"
    assert app.db.execute("SELECT status FROM operations WHERE key='key-timeout'").fetchone()[0] == "confirmed"
    assert app.send("timeout", "key-timeout") == receipt_id
    assert app.db.execute("SELECT calls FROM receiver_calls WHERE key='key-timeout'").fetchone()[0] == 1
    assert app.db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1
    print("PASS timeout recovered in a new process; receiver submissions=1, receipts=1")
    prepare(app, "conflict", "另一份合成文稿。")
    expect_error(ValueError, lambda: app.send("conflict", "key-timeout"))
    print("PASS same key with different payload rejected")
    expect_error(ValueError, lambda: app.send("timeout", "new-key"))
    expect_error(ValueError, lambda: app.revise("timeout", content="不可改写发送历史"))
    print("PASS sent history and original operation key preserved")
    app.close()
    print("SELF-CHECK PASSED: 6 checks; no network or external publishing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-check", action="store_true", help="运行合成数据回归检查")
    group.add_argument("--resume-self-check", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    temp_root = Path(__file__).resolve().parent / ".tmp"
    if args.resume_self_check:
        database = args.resume_self_check.resolve()
        if not database.is_relative_to(temp_root) or not database.is_file():
            parser.error("恢复参数只允许本示例 .tmp 内已经存在的测试数据库。")
        app = Workflow(database)
        print(json.dumps({"receipt_id": app.send("timeout", "key-timeout")}))
        app.close()
    else:
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="self-check-", dir=temp_root) as directory:
            self_check(Path(directory) / "synthetic.sqlite3")


if __name__ == "__main__":
    main()
