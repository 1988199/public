"""向隔离测试队列投递一个有界任务，用于验证正常停机等待。"""
import os
import time
import frappe

os.chdir('/home/frappe/frappe-bench/sites')
frappe.init(site=os.environ['SITE_NAME'], sites_path=os.getcwd())
frappe.connect()
try:
    from frappe.utils.background_jobs import get_queue
    job = get_queue('long').enqueue('time.sleep', 20, job_timeout=60)
    for _ in range(60):
        if str(job.get_status()).lower().endswith('started'):
            print('合成长任务已开始')
            break
        time.sleep(1)
    else:
        raise RuntimeError('worker did not start synthetic task')
finally:
    frappe.destroy()
