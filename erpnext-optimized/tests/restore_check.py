"""主机侧独立恢复演练；仅操作调用方提供的临时测试容器名。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

p = argparse.ArgumentParser()
p.add_argument('--source', required=True)
p.add_argument('--target', required=True)
p.add_argument('--image', required=True)
p.add_argument('--site', required=True)
a = p.parse_args()
if not a.source.startswith('optimized-ci-') or a.target != a.source.removesuffix('-fresh') + '-restore':
    raise ValueError('restore check restricted to synthetic CI containers')
env = os.environ.copy()
env['DB_ROOT_PASSWORD'] = env['ADMIN_PASSWORD'] = env['CI_SITE_PASSWORD']


def run(command, check=True):
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if check and result.returncode:
        # 不打印包含恢复参数或凭据的命令和第三方输出。
        if command[-1] == '/tmp/restore_verify.py':
            diagnostic = json.loads(result.stdout.strip())
            allowed = {'configuration', 'connection', 'customer', 'configuration_marker', 'public_attachment', 'private_attachment'}
            if diagnostic.get('stage') in allowed and str(diagnostic.get('error', '')).isidentifier():
                raise RuntimeError('restore verification failed at ' + diagnostic['stage'] + ': ' + diagnostic['error'])
        raise RuntimeError('synthetic restore operation failed')
    return result


with tempfile.TemporaryDirectory(prefix='runtime-restore-') as temporary:
    folder = Path(temporary)
    run(['docker', 'cp', a.source + ':/tmp/runtime-restore-plan.json', str(folder / 'plan.json')])
    plan = json.loads((folder / 'plan.json').read_text())
    path = plan['folder']
    if not path.startswith('/home/frappe/frappe-bench/sites/' + a.site + '/private/automatic_backups/backup-') or '..' in path:
        raise ValueError('unexpected synthetic backup source')
    run(['docker', 'cp', a.source + ':' + path, str(folder / 'backup')])
    run(['docker', 'run', '-d', '--name', a.target, '--stop-timeout', '600',
         '-e', 'SITE_NAME=' + a.site, '-e', 'BACKUP_ENABLED=0', '-e', 'DB_ROOT_PASSWORD', '-e', 'ADMIN_PASSWORD', a.image])
    for _ in range(120):
        state = run(['docker', 'inspect', '--format', '{{.State.Health.Status}}', a.target]).stdout.strip()
        if state == 'healthy':
            break
        if run(['docker', 'inspect', '--format', '{{.State.Running}}', a.target]).stdout.strip() != 'true':
            raise RuntimeError('synthetic restore container exited')
        time.sleep(5)
    else:
        raise RuntimeError('synthetic restore container not healthy')
    run(['docker', 'exec', a.target, 'supervisorctl', 'stop', 'gunicorn', 'websocket',
         'scheduler', 'worker-short', 'worker-long', 'backup-service'])
    run(['docker', 'cp', str(folder / 'backup'), a.target + ':/tmp/runtime-restore-source'])
    run(['docker', 'exec', a.target, 'chown', '-R', 'frappe:frappe', '/tmp/runtime-restore-source'])
    run(['docker', 'exec', '-u', 'frappe', '-w', '/home/frappe/frappe-bench', a.target,
         '/home/frappe/.local/bin/bench', '--site', a.site, 'restore', '/tmp/runtime-restore-source/database.sql.gz',
         '--with-public-files', '/tmp/runtime-restore-source/public-files.tgz',
         '--with-private-files', '/tmp/runtime-restore-source/private-files.tgz',
         '--db-root-username', 'root', '--db-root-password', env['DB_ROOT_PASSWORD'], '--force'])
    run(['docker', 'cp', str(Path(__file__).with_name('restore_verify.py')), a.target + ':/tmp/restore_verify.py'])
    run(['docker', 'exec', '-u', 'frappe', '-e', 'SITE_NAME=' + a.site, a.target,
         '/home/frappe/frappe-bench/env/bin/python', '/tmp/restore_verify.py'])
    print('隔离恢复演练通过：数据库、两类附件与站点配置；未恢复到任何现场卷')
