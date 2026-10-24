"""仅在构建期配置通用日志与清除旧备份cron；不接触任何运行站点。"""
from pathlib import Path
import json
import re
import subprocess

template = Path('/etc/nginx/nginx.conf.template')
text = template.read_text()
if text.count('http {') != 1:
    raise RuntimeError('unexpected nginx template')
text = text.replace('http {', '''http {
    log_format runtime '$remote_addr - [$time_local] "$request_method $uri $server_protocol" $status $body_bytes_sent';
    access_log /home/frappe/frappe-bench/logs/nginx/access.log runtime;
    error_log /home/frappe/frappe-bench/logs/nginx/error.log warn;''', 1)
template.write_text(text)
old = subprocess.run(['crontab', '-u', 'frappe', '-l'], capture_output=True, text=True)
if old.returncode not in (0, 1):
    raise RuntimeError('cannot inspect image cron')
if old.returncode == 0:
    # 仅剔除bench的旧备份任务，保留其它条目；不启用第二套cron服务。
    rows = [line for line in old.stdout.splitlines() if line.lstrip().startswith('#')
            or not re.search(r'\bbench\b.*\bbackup\b', line)]
    subprocess.run(['crontab', '-u', 'frappe', '-'], input='\n'.join(rows) + '\n', text=True, check=True)
runtime = Path('/opt/erpnext-runtime')
manifest = json.loads((runtime / 'manifest.json').read_text())
manifest['runtime_revision'] = (runtime / 'RUNTIME_REVISION').read_text().strip()
(runtime / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
