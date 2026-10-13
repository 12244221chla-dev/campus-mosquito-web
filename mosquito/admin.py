from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    AreaTreatment, CampusArea, DormCampaign, DormRecord, DormRoom,
    HazardReport, InspectionLog, InspectionPoint,
    CampusMap, AccountProfile,
)


admin.site.site_header = "校园公共卫生管理平台｜运营后台"
admin.site.site_title = "校园公共卫生管理"
admin.site.index_title = "事项、提醒与防蚊协同管理（演示系统）"

admin.site.register(CampusMap)
admin.site.register(AccountProfile)


class HazardReportAdminForm(forms.ModelForm):
    class Meta:
        model = HazardReport
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if data.get("status") == "resolved" and not data.get("processing_note", "").strip():
            self.add_error("processing_note", "标记为已处理时，请填写核查或处置说明。")
        return data


@admin.register(HazardReport)
class HazardReportAdmin(admin.ModelAdmin):
    form = HazardReportAdminForm
    list_display = ("created_at", "location", "kind", "photo_mark", "status", "assigned_point", "is_demo")
    list_filter = ("status", "kind", "is_demo", "created_at")
    search_fields = ("location", "detail", "processing_note")
    readonly_fields = ("id", "photo_preview", "created_at", "updated_at")
    ordering = ("-created_at",)
    fieldsets = (
        ("上报线索", {"fields": ("id", "location", "kind", "detail", "photo_preview", "created_at", "is_demo")}),
        ("核查与处理", {"fields": ("status", "assigned_point", "processing_note", "updated_at")}),
    )

    @admin.display(description="照片", boolean=True)
    def photo_mark(self, obj):
        return bool(obj.photo)

    @admin.display(description="现场照片")
    def photo_preview(self, obj):
        if not obj or not obj.photo:
            return "未上传"
        url = reverse("report-photo", args=[obj.id])
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">'
            '<img src="{}" alt="现场照片" style="max-width:320px;max-height:240px;border-radius:8px">'
            '<br>打开原图</a>', url, url,
        )

@admin.register(InspectionPoint)
class InspectionPointAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "risk", "is_resolved", "is_demo", "updated_at")
    list_filter = ("risk", "is_resolved", "is_demo", "area")
    search_fields = ("name", "area", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(InspectionLog)
class InspectionLogAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "point", "outcome", "inspector", "is_demo")
    list_filter = ("outcome", "is_demo", "occurred_at")
    search_fields = ("point__name", "problem", "action", "inspector")
    readonly_fields = ("created_at",)


@admin.register(CampusArea)
class CampusAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "interval_days", "map_x", "map_y", "is_active", "is_demo")
    list_filter = ("category", "is_active", "is_demo")
    search_fields = ("name", "note")
    fieldsets = (("区域信息", {"fields": ("name", "category", "note", "is_active", "is_demo")}),
                 ("地图与计划", {"fields": ("campus_map", "map_x", "map_y", "interval_days")}))


@admin.register(AreaTreatment)
class AreaTreatmentAdmin(admin.ModelAdmin):
    list_display = ("treated_at", "area", "method", "operator", "is_demo")
    list_filter = ("method", "is_demo", "treated_at", "area")
    search_fields = ("area__name", "operator", "note")
    autocomplete_fields = ("area",)
    readonly_fields = ("created_at",)


@admin.register(DormCampaign)
class DormCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "starts_on", "ends_on", "is_active", "is_demo")
    list_filter = ("is_active", "is_demo")
    search_fields = ("name",)


@admin.register(DormRoom)
class DormRoomAdmin(admin.ModelAdmin):
    list_display = ("building", "room_number", "is_active", "is_demo")
    list_filter = ("building", "is_active", "is_demo")
    search_fields = ("building", "room_number")


class DormRecordAdminForm(forms.ModelForm):
    class Meta:
        model = DormRecord
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if data.get("kind") == "treatment":
            if not data.get("method"):
                self.add_error("method", "请填写经学校允许的处理方式。")
            if not data.get("photo"):
                self.add_error("photo", "宿舍处理记录需要现场凭证照片。")
        return data


@admin.register(DormRecord)
class DormRecordAdmin(admin.ModelAdmin):
    form = DormRecordAdminForm
    list_display = ("created_at", "room", "campaign", "kind", "quantity", "photo_mark", "status", "is_demo")
    list_filter = ("campaign", "kind", "status", "room__building", "is_demo")
    search_fields = ("room__building", "room__room_number", "note", "review_note")
    readonly_fields = ("id", "photo_preview", "created_at", "updated_at")
    fieldsets = (
        ("宿舍登记", {"fields": ("id", "campaign", "room", "kind", "method", "quantity", "photo", "photo_preview", "note", "created_at", "is_demo")}),
        ("后台核对", {"fields": ("status", "review_note", "updated_at")}),
    )

    @admin.display(description="照片", boolean=True)
    def photo_mark(self, obj):
        return bool(obj.photo)

    @admin.display(description="凭证预览")
    def photo_preview(self, obj):
        if not obj or not obj.photo:
            return "未上传"
        url = reverse("dorm-record-photo", args=[obj.id])
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">'
            '<img src="{}" alt="宿舍处理凭证" style="max-width:320px;max-height:240px;border-radius:8px">'
            '<br>打开原图</a>', url, url,
        )
