"""自动提醒巡检命令（生产环境建议由定时任务周期调用）。

    python manage.py run_reminders            # 巡检一次，生成到期 / 超期提醒
    python manage.py run_reminders --dry-run  # 仅统计，不写库
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from pubhealth.models import HealthMatter, OPEN_STATUSES
from pubhealth.services import generate_reminders, reminder_summary


class Command(BaseCommand):
    help = "扫描在办公共卫生事项，按模板时限规则生成自动提醒。"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只统计不写库")

    def handle(self, *args, **options):
        now = timezone.now()
        open_query = HealthMatter.objects.filter(status__in=OPEN_STATUSES).select_related("template")
        if options["dry_run"]:
            pending = reminder_summary(now)
            self.stdout.write(f"[dry-run] 在办事项 {open_query.count()} 条，当前待响应提醒 {pending['pending']} 条。")
            return
        created = generate_reminders(now)
        summary = reminder_summary(now)
        self.stdout.write(self.style.SUCCESS(
            f"巡检完成：新建提醒 {len(created)} 条；累计待响应 {summary['pending']} 条"
            f"（超期 {summary['overdue']} · 升级 {summary['escalate']} · 临期 {summary['warn']}）。"))
        for reminder in created:
            self.stdout.write(f"  · [{reminder.get_level_display()}] {reminder.title}")
