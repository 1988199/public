"""可重复的隔离微基准：只使用合成附件、临时Supervisor及只读Git基线。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
import types

parser = argparse.ArgumentParser()
parser.add_argument('--baseline', default='f716866')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
source = subprocess.check_output(['git', '-c', 'safe.directory=' + str(root), '-C', str(root),
    'show', args.baseline + ':erpnext-optimized/docker/backup_service.py'], text=True)
old = types.ModuleType('baseline_backup')
exec(compile(source, '<public-git-baseline>', 'exec'), old.__dict__)
spec = importlib.util.spec_from_file_location('new_backup', root / 'erpnext-optimized/docker/backup_service.py')
new = importlib.util.module_from_spec(spec)
spec.loader.exec_module(new)


def measure(callback, repeats=3):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        callback()
        samples.append(time.perf_counter() - start)
    return round(statistics.median(samples), 4)


result = {'baseline': args.baseline, 'synthetic_only': True, 'payload_mib': 16, 'median_samples': 3}
with tempfile.TemporaryDirectory(prefix='runtime-benchmark-') as tmp:
    folder = Path(tmp)
    payload = folder / 'payload'
    payload.write_bytes(os.urandom(16 * 1024 * 1024))
    key = os.urandom(32)

    def old_crypto():
        encrypted, restored = folder / 'old.enc', folder / 'old.tar'
        try:
            old.encrypt(payload, encrypted, key)
            old.decrypt(encrypted, restored, key)
            with payload.open('rb') as left, restored.open('rb') as right:
                assert hashlib.file_digest(left, 'sha256').digest() == hashlib.file_digest(right, 'sha256').digest()
        finally:
            encrypted.unlink(missing_ok=True)
            restored.unlink(missing_ok=True)

    def new_crypto():
        encrypted = folder / 'new.enc'
        try:
            expected = new.encrypt(payload, encrypted, key)
            assert new.decrypt_stream(encrypted, key) == expected
        finally:
            encrypted.unlink(missing_ok=True)

    result['authenticated_encryption_seconds'] = {'before': measure(old_crypto), 'after': measure(new_crypto)}
    # 独立Supervisor只管理10个sleep，不启动ERPNext、数据库或网络监听。
    names = 'mariadb redis gunicorn websocket worker-short worker-long scheduler nginx backup-service logrotate-service'.split()
    config = folder / 'supervisord.conf'
    config.write_text(f'''[unix_http_server]
file={folder}/supervisor.sock
[supervisord]
logfile={folder}/supervisor.log
pidfile={folder}/supervisor.pid
childlogdir={folder}
[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix://{folder}/supervisor.sock
''' + ''.join(f'\n[program:{name}]\ncommand=/bin/sleep 180\nstartsecs=0\n' for name in names))
    process = subprocess.Popen(['/usr/bin/supervisord', '-n', '-c', str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if (folder / 'supervisor.sock').exists():
                break
            time.sleep(0.05)
        base = ['/usr/bin/supervisorctl', '-c', str(config), 'status']
        def statuses(batch):
            commands = [base + names] if batch else [base + [name] for name in names]
            for command in commands:
                text = subprocess.check_output(command, text=True)
                assert all(line.split()[1] == 'RUNNING' for line in text.splitlines())
        statuses(True)
        result['supervisor_status_seconds'] = {'before': measure(lambda: statuses(False)), 'after': measure(lambda: statuses(True))}
        result['supervisor_invocations_per_probe'] = {'before': 10, 'after': 1}
    finally:
        process.terminate()
        process.wait(timeout=20)
    result['removed_plaintext_write_bytes_per_encrypted_backup'] = payload.stat().st_size
print(json.dumps(result, indent=2))
