import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class InspectionPoint(models.Model):
    RISK_CHOICES = [(1, "优先排查"), (2, "常规排查"), (3, "低优先级")]

    name = models.CharField(max_length=100, verbose_name="点位名称")
    area = models.CharField(max_length=100, blank=True, verbose_name="所属片区")
    risk = models.PositiveSmallIntegerField(choices=RISK_CHOICES, default=2, verbose_name="排查优先级")
    description = models.TextField(blank=True, verbose_name="环境说明")
    is_resolved = models.BooleanField(default=False, verbose_name="已处理")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "排查点位"
        verbose_name_plural = "排查点位"
        ordering = ("risk", "-created_at")

    def __str__(self):
        return self.name


class HazardReport(models.Model):
    KIND_CHOICES = [
        ("花盆托盘积水", "花盆托盘积水"),
        ("桶盆积水", "桶盆积水"),
        ("废弃瓶罐积水", "废弃瓶罐积水"),
        ("排水处积水", "排水处积水"),
        ("其他环境隐患", "其他环境隐患"),
    ]
    STATUS_CHOICES = [("pending", "待核查"), ("checking", "核查中"), ("resolved", "已处理")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="线索编号")
    location = models.CharField(max_length=80, verbose_name="发现位置")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name="隐患类型")
    detail = models.CharField(max_length=200, blank=True, verbose_name="补充说明")
    photo = models.ImageField(upload_to="reports/%Y/%m/", blank=True, verbose_name="现场照片")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending", verbose_name="处理状态")
    processing_note = models.CharField(max_length=300, blank=True, verbose_name="核查/处置说明")
    assigned_point = models.ForeignKey(
        InspectionPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reports", verbose_name="关联排查点位",
    )
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="提交时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "积水隐患线索"
        verbose_name_plural = "积水隐患线索"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.location}（{self.get_status_display()}）"


class InspectionLog(models.Model):
    OUTCOME_CHOICES = [("open", "待处理"), ("done", "已处理")]

    point = models.ForeignKey(InspectionPoint, on_delete=models.PROTECT, related_name="logs", verbose_name="排查点位")
    problem = models.CharField(max_length=200, verbose_name="发现问题")
    action = models.CharField(max_length=300, verbose_name="处理措施")
    outcome = models.CharField(max_length=8, choices=OUTCOME_CHOICES, default="open", verbose_name="处理结果")
    inspector = models.CharField(max_length=80, blank=True, verbose_name="排查人/班组")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")
    occurred_at = models.DateTimeField(default=timezone.now, verbose_name="排查时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="录入时间")

    class Meta:
        verbose_name = "排查记录"
        verbose_name_plural = "排查记录"
        ordering = ("-occurred_at",)

    def __str__(self):
        return f"{self.point} · {self.occurred_at:%Y-%m-%d}"


class CampusArea(models.Model):
    CATEGORY_CHOICES = [
        ("dining", "饭堂及周边"),
        ("dorm", "宿舍楼及周边"),
        ("teaching", "教学区"),
        ("other", "其他区域"),
    ]

    name = models.CharField(max_length=80, unique=True, verbose_name="区域名称")
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default="other", verbose_name="区域类型")
    map_x = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="示意图横向位置（0-100）",
    )
    map_y = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="示意图纵向位置（0-100）",
    )
    interval_days = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1), MaxValueValidator(365)], verbose_name="计划复查间隔（天）",
    )
    note = models.CharField(max_length=200, blank=True, verbose_name="区域说明")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")

    class Meta:
        verbose_name = "校园消杀区域"
        verbose_name_plural = "校园消杀区域"
        ordering = ("id",)

    def __str__(self):
        return self.name


class AreaTreatment(models.Model):
    METHOD_CHOICES = [
        ("cleanup", "清除积水"),
        ("spray", "专业喷雾消杀"),
        ("fogging", "专业烟雾处理"),
        ("other", "其他经批准措施"),
    ]

    area = models.ForeignKey(CampusArea, on_delete=models.PROTECT, related_name="treatments", verbose_name="处理区域")
    method = models.CharField(max_length=12, choices=METHOD_CHOICES, verbose_name="处理方式")
    treated_at = models.DateTimeField(default=timezone.now, verbose_name="处理时间")
    operator = models.CharField(max_length=80, blank=True, verbose_name="执行单位/人员")
    note = models.CharField(max_length=200, blank=True, verbose_name="处理说明")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="录入时间")

    class Meta:
        verbose_name = "区域消杀记录"
        verbose_name_plural = "区域消杀记录"
        ordering = ("-treated_at",)

    def __str__(self):
        return f"{self.area} · {self.get_method_display()}"


class DormCampaign(models.Model):
    name = models.CharField(max_length=80, verbose_name="批次名称")
    starts_on = models.DateField(verbose_name="开始日期")
    ends_on = models.DateField(verbose_name="结束日期")
    is_active = models.BooleanField(default=True, verbose_name="当前批次")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")

    class Meta:
        verbose_name = "宿舍发放批次"
        verbose_name_plural = "宿舍发放批次"
        ordering = ("-starts_on", "-id")

    def __str__(self):
        return self.name


class DormRoom(models.Model):
    building = models.CharField(max_length=40, verbose_name="宿舍楼")
    room_number = models.CharField(max_length=20, verbose_name="房号")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")

    class Meta:
        verbose_name = "宿舍房间"
        verbose_name_plural = "宿舍房间"
        constraints = [models.UniqueConstraint(fields=["building", "room_number"], name="unique_dorm_room")]
        ordering = ("building", "room_number")

    def __str__(self):
        return f"{self.building} {self.room_number}"


class DormRecord(models.Model):
    KIND_CHOICES = [("pickup", "蚊片领取"), ("treatment", "宿舍灭蚊处理")]
    STATUS_CHOICES = [("pending", "待核对"), ("verified", "已核对"), ("rejected", "未通过")]
    METHOD_CHOICES = [
        ("nonflame", "经批准的非明火措施"),
        ("professional", "专业人员处理"),
        ("other", "其他经批准措施"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="登记编号")
    campaign = models.ForeignKey(DormCampaign, on_delete=models.PROTECT, related_name="records", verbose_name="发放批次")
    room = models.ForeignKey(DormRoom, on_delete=models.PROTECT, related_name="records", verbose_name="宿舍房间")
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, verbose_name="登记类型")
    method = models.CharField(max_length=16, choices=METHOD_CHOICES, blank=True, verbose_name="处理方式")
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(20)], verbose_name="领取数量")
    photo = models.ImageField(upload_to="dorm-records/%Y/%m/", blank=True, verbose_name="现场凭证照片")
    note = models.CharField(max_length=200, blank=True, verbose_name="备注")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending", verbose_name="核对状态")
    review_note = models.CharField(max_length=200, blank=True, verbose_name="核对说明")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="登记时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "宿舍领取与处理登记"
        verbose_name_plural = "宿舍领取与处理登记"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.room} · {self.get_kind_display()}"
