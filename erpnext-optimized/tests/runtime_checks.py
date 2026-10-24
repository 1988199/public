"""只在隔离合成站点执行的运行维护验证，不访问现场数据。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

sys.path.insert(0, '/opt/erpnext-runtime')
import backup_service as backup
import readiness

BENCH = Path('/home/frappe/frappe-bench')
SITE = os.environ['SITE_NAME']


def seed():
    import frappe
    os.chdir(BENCH / 'sites')
    frappe.init(site=SITE, sites_path=str(BENCH / 'sites'))
    frappe.connect()
    try:
        customer = frappe.get_doc({'doctype': 'Customer', 'customer_name': 'Runtime Synthetic Customer',
                                  'customer_type': 'Company'}).insert()
        frappe.db.commit()
        name = customer.name
        for folder in ('public', 'private'):
            files = BENCH / 'sites' / SITE / folder / 'files'
            files.mkdir(parents=True, exist_ok=True)
            (files / 'runtime-synthetic.txt').write_text(folder + '-synthetic')
        config = BENCH / 'sites' / SITE / 'site_config.json'
        values = json.loads(config.read_text())
        values['runtime_synthetic_marker'] = True
        backup.atomic_json(config, values)
        return name
    finally:
        frappe.destroy()


customer = seed()
backup.one_backup()
raw = backup.ROOT / backup.read_status()['last_backup']
backup.verify_raw(raw)
backup.verify_manifest(raw)
if not json.loads((raw / 'site-config.json').read_text()).get('runtime_synthetic_marker'):
    raise RuntimeError('configuration missing from backup')
for name, folder in [('public-files.tgz', 'public'), ('private-files.tgz', 'private')]:
    with tarfile.open(raw / name) as archive:
        found = [x for x in archive if x.name.endswith('runtime-synthetic.txt')]
        if len(found) != 1 or archive.extractfile(found[0]).read().decode() != folder + '-synthetic':
            raise RuntimeError('attachment backup missing')

# 密钥仅在临时容器中随机生成，不打印、不上传。
key = Path('/tmp/runtime-synthetic.key')
key.write_bytes(os.urandom(32))
key.chmod(0o600)
os.environ['BACKUP_ENCRYPTION_KEY_FILE'] = str(key)
os.environ['BACKUP_COPY_DIR'] = '/runtime-copy'
backup.one_backup()
encrypted = backup.ROOT / backup.read_status()['last_backup']
external = Path('/runtime-copy') / SITE / 'runtime-v1' / encrypted.name
if backup.verify_manifest(encrypted) != backup.verify_manifest(external):
    raise RuntimeError('external encrypted copy not identical')
restored_tar = Path('/tmp/runtime-synthetic.tar')
backup.decrypt(external / 'backup.enc', restored_tar, key.read_bytes())
with tarfile.open(restored_tar) as archive:
    config = json.load(archive.extractfile('backup/site-config.json'))
    if not config.get('runtime_synthetic_marker'):
        raise RuntimeError('encrypted copy not recoverable')

# 准备独立恢复容器使用的合成备份位置，不包含凭据值。
Path('/tmp/runtime-restore-plan.json').write_text(json.dumps({'folder': str(raw), 'customer': customer}))
os.environ['REQUIRED_APPS'] = 'runtime_missing_application'
try:
    readiness.check()
except RuntimeError:
    pass
else:
    raise RuntimeError('missing application gate did not reject')
os.environ.pop('REQUIRED_APPS')
os.environ['REQUIRED_MODULES'] = 'runtime_missing_dependency.module'
try:
    readiness.check()
except ModuleNotFoundError:
    pass
else:
    raise RuntimeError('missing dependency gate did not reject')
os.environ.pop('REQUIRED_MODULES')
readiness.check(probe=True)
print('完整备份、数据库压缩流、附件、配置、加密副本、应用门禁及worker心跳验证通过')
