"""服务运行期间每60秒生成站内提醒；免费实例休眠期间不保证巡检。"""
import logging
import threading


def post_worker_init(worker):
    from django.core.management import call_command
    call_command('seed_pubhealth', templates_only=True, verbosity=0)
    stop = threading.Event()
    worker.reminder_stop = stop

    def scan():
        from django.db import close_old_connections
        from pubhealth.services import generate_reminders
        while not stop.is_set():
            close_old_connections()
            try:
                generate_reminders()
            except Exception:
                logging.getLogger(__name__).exception('站内提醒巡检失败，下个周期重试')
            finally:
                close_old_connections()
            stop.wait(60)

    threading.Thread(target=scan, name='public-health-reminders', daemon=True).start()


def worker_exit(server, worker):
    stop = getattr(worker, 'reminder_stop', None)
    if stop:
        stop.set()
