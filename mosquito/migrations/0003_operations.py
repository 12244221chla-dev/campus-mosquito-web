import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("mosquito", "0002_hazardreport_photo")]

    operations = [
        migrations.CreateModel(
            name="CampusArea",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True, verbose_name="区域名称")),
                ("category", models.CharField(choices=[("dining", "饭堂及周边"), ("dorm", "宿舍楼及周边"), ("teaching", "教学区"), ("other", "其他区域")], default="other", max_length=12, verbose_name="区域类型")),
                ("map_x", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name="示意图横向位置（0-100）")),
                ("map_y", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name="示意图纵向位置（0-100）")),
                ("interval_days", models.PositiveSmallIntegerField(default=7, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(365)], verbose_name="计划复查间隔（天）")),
                ("note", models.CharField(blank=True, max_length=200, verbose_name="区域说明")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("is_demo", models.BooleanField(default=True, verbose_name="演示数据")),
            ],
            options={"verbose_name": "校园消杀区域", "verbose_name_plural": "校园消杀区域", "ordering": ("id",)},
        ),
        migrations.CreateModel(
            name="DormCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, verbose_name="批次名称")),
                ("starts_on", models.DateField(verbose_name="开始日期")),
                ("ends_on", models.DateField(verbose_name="结束日期")),
                ("is_active", models.BooleanField(default=True, verbose_name="当前批次")),
                ("is_demo", models.BooleanField(default=True, verbose_name="演示数据")),
            ],
            options={"verbose_name": "宿舍发放批次", "verbose_name_plural": "宿舍发放批次", "ordering": ("-starts_on", "-id")},
        ),
        migrations.CreateModel(
            name="AreaTreatment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("method", models.CharField(choices=[("cleanup", "清除积水"), ("spray", "专业喷雾消杀"), ("fogging", "专业烟雾处理"), ("other", "其他经批准措施")], max_length=12, verbose_name="处理方式")),
                ("treated_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="处理时间")),
                ("operator", models.CharField(blank=True, max_length=80, verbose_name="执行单位/人员")),
                ("note", models.CharField(blank=True, max_length=200, verbose_name="处理说明")),
                ("is_demo", models.BooleanField(default=True, verbose_name="演示数据")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="录入时间")),
                ("area", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="treatments", to="mosquito.campusarea", verbose_name="处理区域")),
            ],
            options={"verbose_name": "区域消杀记录", "verbose_name_plural": "区域消杀记录", "ordering": ("-treated_at",)},
        ),
        migrations.CreateModel(
            name="DormRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("building", models.CharField(max_length=40, verbose_name="宿舍楼")),
                ("room_number", models.CharField(max_length=20, verbose_name="房号")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("is_demo", models.BooleanField(default=True, verbose_name="演示数据")),
            ],
            options={"verbose_name": "宿舍房间", "verbose_name_plural": "宿舍房间", "ordering": ("building", "room_number"), "constraints": [models.UniqueConstraint(fields=("building", "room_number"), name="unique_dorm_room")]},
        ),
        migrations.CreateModel(
            name="DormRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="登记编号")),
                ("kind", models.CharField(choices=[("pickup", "蚊片领取"), ("treatment", "宿舍灭蚊处理")], max_length=12, verbose_name="登记类型")),
                ("method", models.CharField(blank=True, choices=[("nonflame", "经批准的非明火措施"), ("professional", "专业人员处理"), ("other", "其他经批准措施")], max_length=16, verbose_name="处理方式")),
                ("quantity", models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)], verbose_name="领取数量")),
                ("photo", models.ImageField(blank=True, upload_to="dorm-records/%Y/%m/", verbose_name="现场凭证照片")),
                ("note", models.CharField(blank=True, max_length=200, verbose_name="备注")),
                ("status", models.CharField(choices=[("pending", "待核对"), ("verified", "已核对"), ("rejected", "未通过")], default="pending", max_length=10, verbose_name="核对状态")),
                ("review_note", models.CharField(blank=True, max_length=200, verbose_name="核对说明")),
                ("is_demo", models.BooleanField(default=True, verbose_name="演示数据")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="登记时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="records", to="mosquito.dormcampaign", verbose_name="发放批次")),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="records", to="mosquito.dormroom", verbose_name="宿舍房间")),
            ],
            options={"verbose_name": "宿舍领取与处理登记", "verbose_name_plural": "宿舍领取与处理登记", "ordering": ("-created_at",)},
        ),
    ]
