"""运行维护工具；不输出数据库密码，不清理用户旧备份。"""
import argparse
import gzip
import hashlib
import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path

BENCH = Path("/home/frappe/frappe-bench")
SITE = os.environ.get("SITE_NAME", "erp.localhost")


def ready():
    import MySQLdb
    config = json.loads((BENCH / "sites" / SITE / "site_config.json").read_text())
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 6379), timeout=2) as redis:
                redis.sendall(b"*1\r\n$4\r\nPING\r\n")
                if not redis.recv(128).startswith(b"+PONG"):
                    raise ConnectionError("Redis not ready")
            connection = MySQLdb.connect(host=config.get("db_host") or "127.0.0.1",
                                         port=config.get("db_port") or 3306,
                                         user=config.get("db_user") or config["db_name"],
                                         passwd=config["db_password"], db=config["db_name"], connect_timeout=2)
            connection.close()
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("数据库或 Redis 未就绪；请检查服务日志和站点凭据")


def backup():
    import frappe
    os.chdir(BENCH / "sites")
    frappe.init(site=SITE, sites_path=str(BENCH / "sites"))
    frappe.connect()
    try:
        from frappe.utils.backups import BackupGenerator
        folder = Path(os.environ.get("UPGRADE_BACKUP_DIR", str(BENCH / "sites" / SITE / "private" / "runtime_backups")))
        folder = folder / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        folder.mkdir(parents=True, mode=0o700)
        gen = BackupGenerator(frappe.conf.db_name, frappe.conf.db_user, frappe.conf.db_password,
                              db_host=frappe.conf.db_host, db_port=frappe.conf.db_port, db_socket=frappe.conf.db_socket,
                              db_type=frappe.conf.db_type, backup_path=str(folder), ignore_conf=True, compress_files=True)
        gen.get_backup(ignore_files=False, force=True)
        from backup_service import verify_database
        verify_database(Path(gen.backup_path_db))
        files = []
        for attr in ["backup_path_db", "backup_path_files", "backup_path_private_files", "backup_path_conf"]:
            path = Path(getattr(gen, attr))
            with path.open("rb") as file:
                files.append({"name": path.name, "sha256": hashlib.file_digest(file, "sha256").hexdigest()})
        (folder / "manifest.json").write_text(json.dumps({"site": SITE, "files": files}, indent=2))
        print("已生成迁移前备份：", folder)
    finally:
        frappe.destroy()


def check_upgrade():
    current = BENCH / "sites" / SITE / ".optimized-runtime.json"
    desired = json.loads(Path("/opt/erpnext-runtime/manifest.json").read_text())
    if current.exists():
        old = json.loads(current.read_text())
        for app, version in old["apps"].items():
            if app in desired["apps"] and tuple(map(int, version.split("."))) > tuple(map(int, desired["apps"][app].split("."))):
                raise RuntimeError("拒绝应用降级；需要恢复对应数据库备份")
    else:
        # 首次接入优化镜像时，从数据库记录读取旧应用版本，而非新镜像代码版本。
        import frappe
        os.chdir(BENCH / "sites")
        frappe.init(site=SITE, sites_path=str(BENCH / "sites"))
        frappe.connect()
        try:
            if frappe.db.exists("DocType", "Installed Applications"):
                for app in frappe.get_single("Installed Applications").installed_applications:
                    version = app.app_version or ""
                    if app.app_name in desired["apps"] and all(p.isdigit() for p in version.split(".")):
                        if tuple(map(int, version.split("."))) > tuple(map(int, desired["apps"][app.app_name].split("."))):
                            raise RuntimeError("目标应用版本低于数据库记录，拒绝降级")
        finally:
            frappe.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["ready", "backup", "check-upgrade"])
    args = parser.parse_args()
    {"ready": ready, "backup": backup, "check-upgrade": check_upgrade}[args.mode]()
