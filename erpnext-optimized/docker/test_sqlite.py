"""构建门禁：验证 Python 实际加载的 SQLite，而非命令行版本。"""
import sqlite3

assert sqlite3.sqlite_version_info >= (3, 45, 0)
connection = sqlite3.connect(":memory:")
connection.execute('CREATE VIRTUAL TABLE t USING fts5(content, tokenize="trigram remove_diacritics 1")')
connection.execute("INSERT INTO t VALUES (?)", ("冷却设备 café",))
assert connection.execute("SELECT count(*) FROM t WHERE t MATCH ?", ("冷却设",)).fetchone()[0] == 1
assert connection.execute("SELECT count(*) FROM t WHERE t MATCH ?", ("cafe",)).fetchone()[0] == 1
assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("Python SQLite", sqlite3.sqlite_version, "FTS5 trigram + Chinese tests passed")
