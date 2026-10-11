from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from mosquito.models import CampusArea, DormCampaign, DormRoom


AREAS = [
    # Coordinates are approximate positions on the user-provided 2025 campus map.
    ("第一饭堂", "dining", 72, 21),
    ("第二饭堂", "dining", 92, 22),
    ("9栋", "dorm", 85, 22),
    ("8栋", "dorm", 81, 29),
    ("7栋", "dorm", 78, 33),
    ("6栋", "dorm", 73, 36),
    ("5栋", "dorm", 73, 42),
    ("4栋", "dorm", 70, 27),
    ("3栋", "dorm", 69, 31),
    ("2栋", "dorm", 67, 36),
    ("1栋", "dorm", 65, 40),
    ("13栋", "dorm", 88, 10),
    ("14栋", "dorm", 69, 13),
    ("A栋", "teaching", 47, 36),
    ("B栋", "teaching", 50, 41),
    ("C栋", "teaching", 55, 40),
    ("D栋", "teaching", 59, 45),
    ("E栋", "teaching", 59, 52),
    ("F栋", "teaching", 61, 57),
    ("G栋", "teaching", 66, 57),
    ("H栋", "teaching", 62, 57),
    ("体育场", "other", 88, 43),
]


class Command(BaseCommand):
    help = "Create clearly marked demo campus areas, dorm rooms, and an active registration batch."

    def handle(self, *args, **options):
        today = timezone.localdate()
        created_areas = 0
        for name, category, x, y in AREAS:
            _, created = CampusArea.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "map_x": x,
                    "map_y": y,
                    "interval_days": 7,
                    "note": "地图位置为示意，计划间隔仅用于演示；请管理员按授权信息核实。",
                    "is_demo": True,
                },
            )
            created_areas += int(created)

        created_rooms = 0
        for floor in (1, 2):
            for room in range(1, 9):
                _, created = DormRoom.objects.get_or_create(
                    building="9栋",
                    room_number=f"{floor}0{room}",
                    defaults={"is_demo": True},
                )
                created_rooms += int(created)

        month_name = today.strftime("%Y年%m月演示批次")
        _, created_campaign = DormCampaign.objects.get_or_create(
            name=month_name,
            defaults={
                "starts_on": today,
                "ends_on": today + timedelta(days=30),
                "is_active": True,
                "is_demo": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"演示数据就绪：新增区域 {created_areas} 个、房间 {created_rooms} 个，"
            f"当前演示批次{'已创建' if created_campaign else '已存在'}。"
        ))
        self.stdout.write("没有创建任何真实消杀、蚊片领取或宿舍处理记录。")
