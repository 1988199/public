"""扩展应用及当前任务心跳门禁；历史失败计数只报告，不据此停站。"""
import argparse
import importlib
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone

BENCH = Path('/home/frappe/frappe-bench')
SITE = os.environ.get('SITE_NAME', 'erp.localhost')


class ReadinessError(RuntimeError):
    """只包含本模块生成的固定诊断文本，可安全写入健康检查输出。"""


def check(probe=False):
    import frappe
    os.chdir(BENCH / 'sites')
    frappe.init(site=SITE, sites_path=str(BENCH / 'sites'))
    frappe.connect()
    try:
        installed = frappe.get_installed_apps()
        required = os.environ.get('REQUIRED_APPS', '').replace(',', ' ').split()
        if any(not re.fullmatch(r'[a-z][a-z0-9_]*', app) for app in required):
            raise ValueError('invalid REQUIRED_APPS')
        if set(required) - set(installed):
            raise ReadinessError('required application not installed')
        for app in installed:
            importlib.import_module(app)
            importlib.import_module(app + '.hooks')
        modules = os.environ.get('REQUIRED_MODULES', '').replace(',', ' ').split()
        for module in modules:
            if not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*', module):
                raise ValueError('invalid required module')
            importlib.import_module(module)
        if marker := os.environ.get('DEPLOYMENT_READY_FILE'):
            data = json.loads(Path(marker).read_text())
            if data.get('ready') is not True:
                raise ReadinessError('deployment not ready')
        for asset in os.environ.get('REQUIRED_ASSET_PATHS', '').split(','):
            if not asset:
                continue
            path = Path(asset)
            if path.is_absolute() or '..' in path.parts or not (BENCH / 'sites/assets' / path).is_file():
                raise ReadinessError('required asset missing or unsafe')
        result = {'applications_importable': True}
        if probe and os.environ.get('VERIFY_QUEUE_HEARTBEAT', '1') == '1':
            from frappe.utils.background_jobs import get_queue, get_workers
            from rq.registry import FailedJobRegistry
            queues = {}
            max_age = int(os.environ.get('WORKER_HEARTBEAT_MAX_AGE_SECONDS', '300'))
            if max_age < 30:
                raise ValueError('worker heartbeat threshold too small')
            for name in ('short', 'default', 'long'):
                queue = get_queue(name)
                workers = get_workers(queue)
                beats = [w.last_heartbeat for w in workers if w.last_heartbeat]
                ages = [(datetime.now(timezone.utc) - (b if b.tzinfo else b.replace(tzinfo=timezone.utc))).total_seconds() for b in beats]
                if not ages or min(ages) > max_age:
                    raise ReadinessError('worker heartbeat missing or stale')
                # RQ注册表的count属性可能触发过期清理；直接只读查询，保留历史任务。
                queues[name] = {'pending': queue.connection.llen(queue.key),
                                'historical_failed': queue.connection.zcard(FailedJobRegistry(queue=queue).key),
                                'heartbeat_age_seconds': round(min(ages))}
            result['queues'] = queues
        if probe and os.environ.get('BACKUP_ENABLED', '1') == '1':
            path = BENCH / 'sites' / SITE / 'private/automatic_backups/status.json'
            status = json.loads(path.read_text())
            age = time.time() - status.get('last_success', status.get('service_started', 0))
            limit = int(os.environ.get('BACKUP_INTERVAL_SECONDS', '21600')) * 2 + int(os.environ.get('BACKUP_TIMEOUT_SECONDS', '900')) * 3
            if status.get('state') == 'failed' or age > limit:
                raise ReadinessError('automatic backup failed or overdue')
            result['backup_state'] = status.get('state', 'waiting')
        return result
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['imports', 'probe'])
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.mode == 'probe')))
    except Exception as error:
        reason = str(error) if isinstance(error, ReadinessError) else type(error).__name__
        print('readiness check failed: ' + reason, file=sys.stderr)
        sys.exit(1)
