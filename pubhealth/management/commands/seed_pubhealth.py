"""初始化六大公共卫生场景模板，并按需生成演示事项数据。

    python manage.py seed_pubhealth            # 幂等：补齐模板，首次生成演示数据
    python manage.py seed_pubhealth --reset    # 清空演示事项后重新生成
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from pubhealth.models import HealthMatter, MapPoint, Reminder, ScenarioTemplate
from pubhealth.scenarios import SCENARIOS
from pubhealth.services import add_note, assign, create_matter, transition


# 演示事项： (场景编码, 标题, 地点, 情况描述, 问卷, 几天前, 目标状态, 承办单位)
DEMO_MATTERS = [
    ("vector-control", "9栋后方绿化带积水未清", "9栋宿舍楼后方绿地", "花盆托盘与废弃轮胎长期积水，目测有蚊幼虫。",
     {"hazard": "花盆托盘积水", "scale": "30", "mosquito_level": "较多", "measured": "否"}, 1, "processing", "后勤处消杀一班"),
    ("vector-control", "第一饭堂排水沟积水", "第一饭堂东侧排水沟", "排水沟堵塞形成积水，气味明显。",
     {"hazard": "排水处积水", "scale": "12", "mosquito_level": "少量", "measured": "已清除积水"}, 3, "done", "后勤处消杀二班"),
    ("vector-control", "体育馆看台发现成蚊聚集", "体育馆西侧看台", "傍晚时段成蚊密度偏高，已影响晚训。",
     {"hazard": "成蚊密度偏高", "scale": "200", "mosquito_level": "大量", "measured": "否"}, 0, "submitted", ""),
    ("vector-control", "C栋天台废弃瓶罐积水", "C栋教学楼天台", "多处废弃瓶罐积水，未清理。",
     {"hazard": "废弃瓶罐积水", "scale": "8", "mosquito_level": "少量", "measured": "否"}, 6, "done", "后勤处消杀一班"),
    ("vector-control", "5栋一楼水房桶盆积水", "5栋宿舍一楼水房", "清洁用桶长期存水。",
     {"hazard": "桶盆积水", "scale": "3", "mosquito_level": "未发现", "measured": "已通知宿管"}, 9, "rejected", ""),
    ("infectious-report", "同宿舍2人发热", "8栋 302", "同一宿舍连续两天出现发热，最高38.6℃。",
     {"symptom": "发热", "temperature": "38.6", "people": "2", "visited": "已就诊", "cluster": "是"}, 1, "processing", "校医室"),
    ("infectious-report", "班级3人腹泻", "B栋 高二(3)班", "同班3名学生出现腹泻呕吐症状。",
     {"symptom": "腹泻 / 呕吐", "temperature": "37.4", "people": "3", "visited": "未就诊", "cluster": "是"}, 0, "submitted", ""),
    ("infectious-report", "1例皮疹待排查", "6栋 108", "学生躯干出现皮疹，已到校医室初筛。",
     {"symptom": "皮疹", "temperature": "36.8", "people": "1", "visited": "已就诊", "cluster": "否"}, 4, "done", "校医室"),
    ("infectious-report", "食堂从业人员咽痛", "第一饭堂后厨", "1名从业人员咽痛，已调离直接接触岗位。",
     {"symptom": "咳嗽 / 咽痛", "temperature": "37.2", "people": "1", "visited": "已就诊", "cluster": "否"}, 2, "accepted", "校医室"),
    ("hygiene-inspection", "食堂后厨卫生专项检查", "第一饭堂后厨", "抽检发现地面积油、生熟分隔不规范。",
     {"scope": "食堂后厨", "score": "72", "problem": "地面积油、生熟砧板未分开、留样记录缺 2 天", "deadline": "3个工作日内"}, 2, "processing", "爱卫办"),
    ("hygiene-inspection", "9栋宿舍卫生抽查", "9栋宿舍 2 层", "抽查 8 间，2 间内务不达标。",
     {"scope": "学生宿舍", "score": "84", "problem": "杂物堆放、阳台积水", "deadline": "24小时内"}, 5, "done", "宿管中心"),
    ("hygiene-inspection", "公共卫生间卫生检查", "A栋一至三楼卫生间", "部分卫生间清洁频次不足。",
     {"scope": "公共卫生间", "score": "78", "problem": "洗手台水渍、垃圾清运不及时", "deadline": "一周内"}, 1, "review", "后勤处保洁组"),
    ("area-disinfection", "B栋教学楼公共区预防性消毒", "B栋教学楼", "按要求对走廊、扶手、卫生间开展预防性消毒。",
     {"scope": "教学楼公共区", "method": "含氯消毒剂擦拭", "agent": "84 消毒液 1:100", "area_size": "1200"}, 1, "review", "后勤处消毒组"),
    ("area-disinfection", "第一饭堂就餐区终末消毒", "第一饭堂就餐区", "出现腹泻聚集后开展终末消毒。",
     {"scope": "食堂就餐区", "method": "超低容量喷雾", "agent": "过氧化氢消毒液", "area_size": "800"}, 1, "done", "后勤处消毒组"),
    ("area-disinfection", "图书馆阅览区消毒", "图书馆二楼阅览区", "例行预防性消毒。",
     {"scope": "图书馆", "method": "含氯消毒剂擦拭", "agent": "84 消毒液 1:200", "area_size": "600"}, 3, "accepted", "后勤处消毒组"),
    ("area-disinfection", "电梯轿厢每日消毒", "A栋教学楼电梯", "电梯按钮与轿厢需每日消毒。",
     {"scope": "电梯 / 楼梯间", "method": "含氯消毒剂擦拭", "agent": "75% 酒精 / 84 稀释液", "area_size": "8"}, 0, "submitted", ""),
    ("health-education", "秋冬季呼吸道传染病防控讲座", "学生活动中心", "面向全校学生开展专题讲座。",
     {"topic": "秋冬季呼吸道传染病防控", "form": "主题讲座", "audience": "全体学生", "reach": "450"}, 2, "done", "校医室 · 宣传部"),
    ("health-education", "宿舍防蚊科普班会", "9栋宿舍活动室", "结合消杀工作讲解清积水要点。",
     {"topic": "基孔肯雅热防控 · 清积水", "form": "主题班会", "audience": "住宿生", "reach": "180"}, 1, "processing", "宿管中心"),
    ("health-education", "食堂从业人员手卫生培训", "第一饭堂会议室", "针对从业人员开展洗手与消毒培训。",
     {"topic": "手卫生与食品卫生", "form": "主题讲座", "audience": "食堂从业人员", "reach": "60"}, 5, "done", "后勤处"),
    ("health-education", "健康教育宣传栏更新", "教学楼 A 栋一楼", "更换宣传栏，张贴防蚊与防流感海报。",
     {"topic": "防蚊灭蚊 + 流感预防", "form": "宣传海报", "audience": "全体学生", "reach": "2000"}, 0, "accepted", "宣传部"),
    ("emergency-report", "同班级聚集性发热（已上报）", "B栋 高二(3)班", "同一班级 5 人发热，启动应急预案。",
     {"level": "较大事件", "people": "5", "measure": "已停课、已隔离、已对教室消毒", "contact": "李老师 / 年级组长 / 138****0000"}, 0, "processing", "应急处置组"),
    ("emergency-report", "食堂疑似食源性不适（已终末消毒）", "第一饭堂", "多名就餐学生出现腹泻，已按预案处置。",
     {"level": "一般事件", "people": "7", "measure": "已留样、已终末消毒、已上报疾控", "contact": "王医生 / 校医室 / 137****1111"}, 2, "done", "应急处置组"),
    ("emergency-report", "宿舍楼自来水异味核查", "5栋宿舍", "学生反映自来水有异味，需应急核查。",
     {"level": "一般事件", "people": "0", "measure": "已通知后勤停水核查", "contact": "张师傅 / 后勤处 / 136****2222"}, 1, "processing", "应急处置组"),
]


# 地图演示点位： (名称, 类型, x%, y%, 状态, 说明)  —— 演示「用户可以自定义点位」
AREA_CATEGORY_MAP = {"dining": "canteen", "dorm": "dorm", "teaching": "teaching", "other": "other"}
DEMO_MAP_POINTS = [
    ("南门快递点旁废弃水桶", "water", 22.5, 74.0, "pending", "学生新报备的积水点，待安排消杀"),
    ("图书馆北侧绿化带", "green", 61.0, 33.0, "done", "已完成喷雾消杀，留存处理凭证"),
    ("第二饭堂后垃圾房", "garbage", 47.5, 58.0, "pending", "垃圾清运不及时，需消杀除臭"),
    ("体育馆器材室后侧排水沟", "water", 78.0, 46.5, "done", "已清除积水并投放灭蚊幼剂"),
]


class Command(BaseCommand):
    help = "初始化公共卫生场景模板并生成演示事项数据。"

    def add_arguments(self, parser):
        parser.add_argument('--templates-only', action='store_true', help='只补齐场景模板，不导入虚构事项或处理状态')
        parser.add_argument("--reset", action="store_true", help="先清空演示事项与提醒再重新生成")
        parser.add_argument("--real-points", action="store_true",
                            help="地图点位只依据真实处理记录判定状态（不使用演示分布）")

    def handle(self, *args, **options):
        templates = {}
        created_templates = 0
        for item in SCENARIOS:
            template, created = ScenarioTemplate.objects.get_or_create(
                code=item["code"],
                defaults={**item, "is_demo": True},
            )
            templates[template.code] = template
            created_templates += int(created)
        self.stdout.write(self.style.SUCCESS(
            f"场景模板就绪：共 {len(templates)} 个（新增 {created_templates} 个）。"))
        if options['templates_only']:
            return

        if options["reset"]:
            removed = HealthMatter.objects.filter(is_demo=True).count()
            Reminder.objects.filter(matter__is_demo=True).delete()
            HealthMatter.objects.filter(is_demo=True).delete()
            MapPoint.objects.filter(is_demo=True).delete()
            self.stdout.write(f"已清空演示事项 {removed} 条。")

        self._seed_map_points(real_only=options["real_points"])
        if not options["reset"] and HealthMatter.objects.filter(is_demo=True).exists():
            self.stdout.write("已存在演示事项，如需重建请加 --reset。")
            self._report()
            return

        random.seed(20261012)
        now = timezone.now()
        for code, title, location, detail, payload, days_ago, target, handler in DEMO_MATTERS:
            template = templates[code]
            submitted_at = now - timedelta(days=days_ago, hours=random.randint(1, 6))
            matter = create_matter(
                template, title=title, location=location, detail=detail, payload=payload,
                reporter_name=random.choice(["值班教师", "宿管员", "校医室", "学生会生活部", "后勤巡查"]),
                reporter_contact="", source=random.choice(["web", "app", "scan"]),
                submitted_at=submitted_at, is_demo=True, actor_name="演示报备人",
            )
            self._progress(matter, target, handler, submitted_at, template)
        self._report()

    def _seed_map_points(self, real_only=False):
        """把校园原有消杀区域导入为地图点位，并补充若干自定义演示点位。

        状态判定只看「有没有处理到位」：最近一次处理仍在计划间隔内 → 已处理（绿点），
        从未处理或已超过计划间隔 → 未处理（红点），保证地图上一眼看清待办。
        演示库通常没有历史处理记录，此时按固定规则生成可复现的演示分布，
        避免出现「整张图全红」；加 --real-points 可只用真实处理记录判定。
        """
        from mosquito.models import CampusArea
        from pubhealth.services import create_map_point

        today = timezone.localdate()
        imported = 0
        for area in CampusArea.objects.filter(is_active=True).prefetch_related("treatments"):
            ref = f"area:{area.id}"
            if MapPoint.objects.filter(source_ref=ref).exists():
                continue
            records = sorted(area.treatments.all(), key=lambda row: row.treated_at, reverse=True)
            latest = records[0] if records else None
            status, note, last_done_at = "pending", "暂无处理记录，待安排消杀", None
            if latest:
                last_date = timezone.localtime(latest.treated_at).date()
                days = (today - last_date).days
                last_done_at = latest.treated_at
                if days <= area.interval_days:
                    status = "done"
                    note = f"最近处理 {last_date.isoformat()}（{days} 天前），仍在 {area.interval_days} 天计划间隔内"
                else:
                    note = f"距上次处理 {days} 天，已超过 {area.interval_days} 天计划间隔，需再次消杀"
            elif not real_only:
                days = (area.id * 2) % 6 + 1
                if area.id % 3:
                    status, last_done_at = "done", timezone.now() - timedelta(days=days, hours=3)
                    note = f"演示数据：最近处理于 {days} 天前，仍在 {area.interval_days} 天计划间隔内"
                else:
                    note = f"演示数据：距上次处理已超 {area.interval_days} 天计划间隔，需再次消杀"
            create_map_point(
                name=area.name,
                category=AREA_CATEGORY_MAP.get(area.category, "other"),
                map_x=area.map_x, map_y=area.map_y, note=note, source_ref=ref,
                operator_name="系统预置", is_custom=False, is_demo=True,
                status=status, last_done_at=last_done_at,
            )
            imported += 1

        custom = 0
        for name, category, x, y, status, note in DEMO_MAP_POINTS:
            if MapPoint.objects.filter(name=name, is_demo=True).exists():
                continue
            create_map_point(
                name=name, category=category, map_x=x, map_y=y, note=note,
                operator_name="演示报备人", is_custom=True, is_demo=True, status=status,
                last_done_at=timezone.now() - timedelta(days=2) if status == "done" else None,
            )
            custom += 1
        stats = MapPoint.objects.count()
        done = MapPoint.objects.filter(status="done").count()
        self.stdout.write(self.style.SUCCESS(
            f"地图点位：共 {stats} 个（本轮导入区域 {imported} 个、自定义 {custom} 个），"
            f"已处理 {done} 个 / 未处理 {stats - done} 个。"))

    def _progress(self, matter, target, handler, submitted_at, template):
        """把演示事项推进到目标状态，并补齐可追溯流水。"""
        if target == "submitted":
            return
        if target == "rejected":
            transition(matter, "rejected", actor_name="演示管理者", note="现场核查未发现隐患，予以退回。",
                       occurred_at=submitted_at + timedelta(hours=template.accept_sla_hours + 2))
            return
        transition(matter, "accepted", actor_name="演示管理者", note="已受理并分派承办。",
                   occurred_at=submitted_at + timedelta(hours=max(1, template.accept_sla_hours // 2)))
        if handler:
            assign(matter, handler_name=handler, actor_name="演示管理者")
        if target == "accepted":
            return
        transition(matter, "processing", actor_name=handler or "承办单位", note="已到场处置，正在跟进。",
                   occurred_at=submitted_at + timedelta(hours=template.accept_sla_hours + 3))
        if target == "processing":
            return
        transition(matter, "review", actor_name=handler or "承办单位", note="处置完成，提交凭证待复核。",
                   occurred_at=submitted_at + timedelta(hours=template.accept_sla_hours + 8))
        if target == "review":
            return
        transition(matter, "done", actor_name="演示复核人", kind="review", note="复核通过，事项办结归档。",
                   occurred_at=submitted_at + timedelta(hours=template.total_sla_hours - 2))

    def _report(self):
        from pubhealth.services import generate_reminders
        created = generate_reminders()
        total = HealthMatter.objects.count()
        demo = HealthMatter.objects.filter(is_demo=True).count()
        overdue = sum(1 for m in HealthMatter.objects.all() if m.is_overdue)
        self.stdout.write(self.style.SUCCESS(
            f"演示事项：共 {total} 条（演示 {demo} 条），自动提醒新增 {len(created)} 条，当前超期 {overdue} 条。"))
        points = MapPoint.objects.count()
        self.stdout.write(f"地图点位：共 {points} 个，其中未处理（红点）{MapPoint.objects.filter(status='pending').count()} 个。")
        self.stdout.write("演示数据仅供参考，不代表学校真实业务情况。")
