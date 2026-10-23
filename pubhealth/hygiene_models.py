"""Dorm inspection records: human scoring, private evidence, approved membership."""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class DormBinding(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='学生账号')
    room = models.ForeignKey('mosquito.DormRoom', on_delete=models.PROTECT, verbose_name='申请宿舍')
    approved = models.BooleanField(default=False, verbose_name='管理员已确认')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = '学生宿舍绑定'

    def __str__(self):
        return f'{self.user} · {self.room}'


class HygieneInspector(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='学生账号')
    active = models.BooleanField(default=True, verbose_name='允许检查评分')

    class Meta:
        verbose_name = verbose_name_plural = '卫生检查学生授权'

    def __str__(self):
        return str(self.user)


class DormInspection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission_key = models.CharField(max_length=64, unique=True, editable=False)
    room = models.ForeignKey('mosquito.DormRoom', on_delete=models.PROTECT, verbose_name='宿舍')
    room_label = models.CharField(max_length=80, verbose_name='检查时宿舍')
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='检查学生')
    inspected_on = models.DateField(verbose_name='检查日期')
    items = models.JSONField(verbose_name='逐项评分')
    score = models.PositiveSmallIntegerField(verbose_name='总分')
    passed = models.BooleanField(verbose_name='合格')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='记录时间')

    class Meta:
        verbose_name = verbose_name_plural = '宿舍卫生检查档案'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.room_label} · {self.inspected_on} · {self.score}分'


class HygieneEvidence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    inspection = models.ForeignKey(DormInspection, null=True, blank=True, on_delete=models.PROTECT, related_name='evidence')
    item_key = models.CharField(max_length=20)
    photo = models.ImageField(upload_to='hygiene/%Y/%m/')
    created_at = models.DateTimeField(auto_now_add=True)
