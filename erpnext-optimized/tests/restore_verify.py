"""仅在隔离恢复容器中合并合成配置，并验证合成业务及附件。"""
import json
import os
import sys
from pathlib import Path
import frappe

bench = Path('/home/frappe/frappe-bench')
site = os.environ['SITE_NAME']
folder = Path('/tmp/runtime-restore-source')
target = bench / 'sites' / site / 'site_config.json'
stage = 'configuration'
try:
    current = json.loads(target.read_text())
    source = json.loads((folder / 'site-config.json').read_text())
    db_fields = {'db_name', 'db_user', 'db_password', 'db_host', 'db_port', 'db_socket', 'db_type'}
    values = {k: v for k, v in source.items() if k not in db_fields}
    values.update({k: v for k, v in current.items() if k in db_fields})
    target.write_text(json.dumps(values))
    target.chmod(0o600)
    os.chdir(bench / 'sites')
    stage = 'connection'
    frappe.init(site=site, sites_path=str(bench / 'sites'))
    frappe.connect()
    stage = 'customer'
    if frappe.db.count('Customer', {'customer_name': 'Runtime Synthetic Customer'}) != 1:
        raise RuntimeError('restored synthetic database mismatch')
    stage = 'configuration_marker'
    if frappe.conf.runtime_synthetic_marker is not True:
        raise RuntimeError('restored configuration mismatch')
    for kind in ('public', 'private'):
        stage = kind + '_attachment'
        if (bench / 'sites' / site / kind / 'files/runtime-synthetic.txt').read_text() != kind + '-synthetic':
            raise RuntimeError('restored attachment mismatch')
    print('独立恢复容器的数据库、公共/私有附件与配置核验通过')
except Exception as error:
    # 固定阶段名及异常类型，不输出站点配置、备份内容或第三方异常消息。
    print(json.dumps({'stage': stage, 'error': type(error).__name__}))
    sys.exit(1)
finally:
    frappe.destroy()
