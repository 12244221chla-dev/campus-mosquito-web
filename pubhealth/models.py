"""通用公共卫生事项引擎 —— 数据模型。

设计目标（对应项目核心价值）：
1. 场景可扩展：新增业务场景只需新增一条 ScenarioTemplate，不改代码结构。
2. 数据可追溯：任何状态流转 / 备注 / 分派 / 提醒都写入 MatterEvent 事件流水，形成不可篡改的办理轨迹。
3. 自动提醒：Reminder 由引擎按模板时限规则自动生成，带幂等去重键，可线上确认闭环。
"""

import uuid

from .hygiene_models import DormBinding, HygieneInspector, DormInspection, HygieneEvidence

from django.conf import settings
from django.db import models
from django.utils import timezone


# 事项的通用状态流（线性主干 + 退回支线）。各场景可在模板里自定义阶段名称。
STATUS_ORDER = ["submitted", "accepted", "processing", "review", "done"]
OPEN_STATUSES = ("submitted", "accepted", "processing", "review")


class ScenarioTemplate(models.Model):
    """公共卫生场景模板：定义一类事项的报备字段、办理阶段、时限与提醒规则。"""

    CATEGORY_CHOICES = [
        ("vector", "媒介生物防制"),
        ("infectious", "传染病防控"),
        ("inspection", "卫生检查"),
        ("disinfection", "消毒作业"),
        ("education", "健康宣教"),
        ("emergency", "应急处置"),
    ]
    UNIT_CHOICES = [("hours", "小时"), ("days", "天")]

    code = models.SlugField(max_length=40, unique=True, verbose_name="场景编码")
    code_prefix = models.CharField(max_length=6, verbose_name="事项编号前缀")
    name = models.CharField(max_length=60, verbose_name="场景名称")
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default="inspection", verbose_name="业务分类")
    icon = models.CharField(max_length=8, default="◆", verbose_name="图标识记")
    color = models.CharField(max_length=16, default="#155b5d", verbose_name="主题色")
    summary = models.CharField(max_length=200, blank=True, verbose_name="场景说明")
    fields_schema = models.JSONField(default=list, blank=True, verbose_name="报备字段定义")
    stages = models.JSONField(default=list, blank=True, verbose_name="办理阶段定义")
    accept_sla_hours = models.PositiveIntegerField(default=24, verbose_name="受理时限（小时）")
    handle_sla_hours = models.PositiveIntegerField(default=72, verbose_name="处置时限（小时）")
    reminder_lead_hours = models.PositiveIntegerField(default=12, verbose_name="到期前提醒（小时）")
    escalate_hours = models.PositiveIntegerField(default=24, verbose_name="超期升级（小时）")
    requires_photo = models.BooleanField(default=False, verbose_name="报备需照片")
    requires_review = models.BooleanField(default=True, verbose_name="办结需复核")
    is_emergency = models.BooleanField(default=False, verbose_name="应急类（抢占顶栏）")
    sort_order = models.PositiveSmallIntegerField(default=100, verbose_name="排序")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    is_demo = models.BooleanField(default=True, verbose_name="演示数据")

    class Meta:
        verbose_name = "公共卫生场景模板"
        verbose_name_plural = "公共卫生场景模板"
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.name

    @property
    def total_sla_hours(self):
        return self.accept_sla_hours + self.handle_sla_hours

    def stage_list(self):
        """返回该场景启用的阶段列表，缺省回落到通用五段。"""
        if self.stages:
            return self.stages
        return [
            {"key": key, "name": dict(HealthMatter.STATUS_CHOICES)[key], "desc": ""}
            for key in STATUS_ORDER
        ]

    def stage_names(self):
        return {item["key"]: item.get("name") or dict(HealthMatter.STATUS_CHOICES).get(item["key"], item["key"])
                for item in self.stage_list()}

    def field_list(self):
        return list(self.fields_schema or [])


class HealthMatter(models.Model):
    """公共卫生事项（报备单）：所有场景共用同一张表，差异由模板字段承载。"""

    STATUS_CHOICES = [
        ("submitted", "待受理"),
        ("accepted", "已受理"),
        ("processing", "处理中"),
        ("review", "待复核"),
        ("done", "已完成"),
        ("rejected", "已退回"),
    ]
    PRIORITY_CHOICES = [("low", "低"), ("normal", "常规"), ("high", "较高"), ("urgent", "紧急")]
    SOURCE_CHOICES = [
        ("web", "线上报备"),
        ("app", "移动端"),
        ("admin", "后台录入"),
        ("scan", "现场扫码"),
        ("system", "系统生成"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="内部编号")
    code = models.CharField(max_length=24, unique=True, db_index=True, verbose_name="事项编号")
    template = models.ForeignKey(ScenarioTemplate, on_delete=models.PROTECT, related_name="matters", verbose_name="场景模板")
    title = models.CharField(max_length=120, verbose_name="事项标题")
    location = models.CharField(max_length=100, verbose_name="发生地点")
    detail = models.TextField(blank=True, verbose_name="情况描述")
    payload = models.JSONField(default=dict, blank=True, verbose_name="场景问卷数据")
    photo = models.ImageField(upload_to="matters/%Y/%m/", blank=True, verbose_name="现场照片")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="submitted", verbose_name="当前状态")
    priority = models.CharField(max_length=8, choices=PRIORITY_CHOICES, default="normal", verbose_name="优先级")
    source = models.CharField(max_length=8, choices=SOURCE_CHOICES, default="web", verbose_name="报备来源")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="reported_matters", verbose_name="报备账号")
    reporter_name = models.CharField(max_length=60, blank=True, verbose_name="报备人")
    reporter_contact = models.CharField(max_length=60, blank=True, verbose_name="联系方式")
    handler = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="handled_matters", verbose_name="承办账号")
    handler_name = models.CharField(max_length=80, blank=True, verbose_name="承办单位 / 人员")
    is_demo = models.BooleanField(default=False, verbose_name="演示数据")
    submitted_at = models.DateTimeField(default=timezone.now, verbose_name="报备时间")
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name="受理时间")
    due_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="处置到期时间")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="办结时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="写入时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="最后更新")

    class Meta:
        verbose_name = "公共卫生事项"
        verbose_name_plural = "公共卫生事项"
        ordering = ("-submitted_at", "-id")
        indexes = [
            models.Index(fields=["status", "-submitted_at"]),
            models.Index(fields=["template", "-submitted_at"]),
        ]

    def __str__(self):
        return f"{self.code} {self.title}"

    # ---- 派生状态 ----
    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    @property
    def is_overdue(self):
        return bool(self.is_open and self.due_at and timezone.now() > self.due_at)

    @property
    def status_name(self):
        return self.template.stage_names().get(self.status, self.get_status_display())

    @property
    def progress_percent(self):
        """基于状态在主干流程中的位置给出完成度，用于可视化进度条。"""
        if self.status == "rejected":
            return 0
        if self.status == "done":
            return 100
        try:
            index = STATUS_ORDER.index(self.status)
        except ValueError:
            return 0
        return round(index / (len(STATUS_ORDER) - 1) * 100)

    @property
    def remaining_hours(self):
        if not self.is_open or not self.due_at:
            return None
        return (self.due_at - timezone.now()).total_seconds() / 3600

    @property
    def age_hours(self):
        end = self.closed_at or timezone.now()
        return (end - self.submitted_at).total_seconds() / 3600

    @property
    def urgency(self):
        """用于列表着色：overdue / urgent / soon / normal。"""
        if self.is_overdue:
            return "overdue"
        remaining = self.remaining_hours
        if remaining is None:
            return "normal"
        if remaining <= 6:
            return "urgent"
        if remaining <= self.template.reminder_lead_hours:
            return "soon"
        return "normal"


class MapPoint(models.Model):
    """消杀点位：校园地图上的可自定义点位。

    只保留两种一眼可辨的处理状态：
        done    已处理 —— 绿点
        pending 未处理 —— 红点
    点位坐标用相对底图的百分比保存（0-100），因此换底图或缩放都不会错位；
    用户可以在地图上直接点选位置新增自定义点位，也可以把已有预置点位纳入统一台账。
    """

    STATUS_CHOICES = [("done", "已处理"), ("pending", "未处理")]
    CATEGORY_CHOICES = [
        ("water", "积水隐患点"),
        ("garbage", "垃圾收集点"),
        ("green", "绿化带"),
        ("toilet", "公共卫生间"),
        ("dorm", "宿舍区"),
        ("canteen", "食堂餐饮"),
        ("teaching", "教学办公区"),
        ("other", "其他点位"),
    ]

    campus_map = models.ForeignKey('mosquito.CampusMap', null=True, blank=True, on_delete=models.PROTECT, verbose_name="所属地图")
    name = models.CharField(max_length=60, verbose_name="点位名称")
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default="other", verbose_name="点位类型")
    map_x = models.FloatField(default=50.0, verbose_name="横向位置（底图百分比 0-100）")
    map_y = models.FloatField(default=50.0, verbose_name="纵向位置（底图百分比 0-100）")
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="pending", verbose_name="处理状态")
    note = models.CharField(max_length=180, blank=True, verbose_name="点位说明")
    is_custom = models.BooleanField(default=True, verbose_name="自定义点位")
    source_ref = models.CharField(max_length=40, blank=True, verbose_name="来源引用（预置点位回填）")
    last_done_at = models.DateTimeField(null=True, blank=True, verbose_name="最近处理时间")
    last_action_by = models.CharField(max_length=60, blank=True, verbose_name="最近操作人")
    created_by_name = models.CharField(max_length=60, blank=True, verbose_name="登记人")
    is_demo = models.BooleanField(default=False, verbose_name="演示数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="最后更新")

    class Meta:
        verbose_name = "消杀点位"
        verbose_name_plural = "消杀点位"
        ordering = ("-updated_at", "-id")
        indexes = [models.Index(fields=["status", "-updated_at"])]

    def __str__(self):
        return f"{self.name}（{self.get_status_display()}）"

    @property
    def is_done(self):
        return self.status == "done"

    @property
    def status_name(self):
        return self.get_status_display()


class MatterEvent(models.Model):
    """事项事件流水 —— 数据可追溯的基石。状态流转、分派、备注、提醒、复核全部落流水。"""

    KIND_CHOICES = [
        ("created", "报备提交"),
        ("status", "状态流转"),
        ("assign", "分派承办"),
        ("note", "进展备注"),
        ("attachment", "补充材料"),
        ("reminder", "系统提醒"),
        ("review", "复核意见"),
        ("reopen", "重新打开"),
    ]

    matter = models.ForeignKey(HealthMatter, on_delete=models.CASCADE, related_name="events", verbose_name="所属事项")
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default="note", verbose_name="事件类型")
    from_status = models.CharField(max_length=12, blank=True, verbose_name="原状态")
    to_status = models.CharField(max_length=12, blank=True, verbose_name="新状态")
    note = models.CharField(max_length=300, blank=True, verbose_name="说明")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="操作账号")
    actor_name = models.CharField(max_length=60, blank=True, verbose_name="操作人")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="发生时间")

    class Meta:
        verbose_name = "事项办理流水"
        verbose_name_plural = "事项办理流水"
        ordering = ("created_at", "id")

    def __str__(self):
        return f"{self.matter.code} · {self.get_kind_display()}"


class Reminder(models.Model):
    """自动提醒：由引擎按模板时限规则生成，带幂等去重键，可线上确认闭环。"""

    LEVEL_CHOICES = [("info", "提示"), ("warn", "临期"), ("overdue", "超期"), ("escalate", "升级")]
    STATUS_CHOICES = [("pending", "待响应"), ("ack", "已确认"), ("closed", "已消除")]
    RULE_CHOICES = [
        ("accept_sla", "受理超时"),
        ("due_soon", "临近到期"),
        ("overdue", "已超期"),
        ("escalated", "超期升级"),
        ("digest", "每日汇总"),
    ]

    matter = models.ForeignKey(HealthMatter, on_delete=models.CASCADE, related_name="reminders", verbose_name="关联事项")
    rule = models.CharField(max_length=16, choices=RULE_CHOICES, verbose_name="触发规则")
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default="warn", verbose_name="提醒级别")
    title = models.CharField(max_length=140, verbose_name="提醒标题")
    body = models.CharField(max_length=300, blank=True, verbose_name="提醒内容")
    dedup_key = models.CharField(max_length=90, unique=True, verbose_name="去重键")
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="pending", verbose_name="提醒状态")
    due_at = models.DateTimeField(null=True, blank=True, verbose_name="提醒基准时间")
    triggered_at = models.DateTimeField(default=timezone.now, verbose_name="触发时间")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="推送时间")
    channel = models.CharField(max_length=16, default="inapp", verbose_name="推送渠道")
    ack_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="确认账号")
    ack_name = models.CharField(max_length=60, blank=True, verbose_name="确认人")
    ack_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "自动提醒"
        verbose_name_plural = "自动提醒"
        ordering = ("-triggered_at", "-id")
        indexes = [models.Index(fields=["status", "-triggered_at"])]

    def __str__(self):
        return f"[{self.get_level_display()}] {self.title}"
