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
            raise RuntimeError('required application not installed')
        for app in installed:
            importlib.import_module(app)
            importlib.import_module(app + '.hooks')
        if marker := os.environ.get('DEPLOYMENT_READY_FILE'):
            data = json.loads(Path(marker).read_text())
            if data.get('ready') is not True:
                raise RuntimeError('deployment not ready')
        for asset in os.environ.get('REQUIRED_ASSET_PATHS', '').split(','):
            if not asset:
                continue
            path = Path(asset)
            if path.is_absolute() or '..' in path.parts or not (BENCH / 'sites/assets' / path).is_file():
                raise RuntimeError('required asset missing or unsafe')
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
                    raise RuntimeError('worker heartbeat missing or stale')
                queues[name] = {'pending': queue.count, 'historical_failed': FailedJobRegistry(queue=queue).count,
                                'heartbeat_age_seconds': round(min(ages))}
            result['queues'] = queues
        if probe and os.environ.get('BACKUP_ENABLED', '1') == '1':
            path = BENCH / 'sites' / SITE / 'private/automatic_backups/status.json'
            status = json.loads(path.read_text())
            age = time.time() - status.get('last_success', status.get('service_started', 0))
            limit = int(os.environ.get('BACKUP_INTERVAL_SECONDS', '21600')) * 2 + int(os.environ.get('BACKUP_TIMEOUT_SECONDS', '900')) * 3
            if status.get('state') == 'failed' or age > limit:
                raise RuntimeError('automatic backup failed or overdue')
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
        print('readiness check failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
