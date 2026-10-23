from django.contrib import admin
from django.utils.html import format_html

from .models import HealthMatter, MapPoint, MatterEvent, Reminder, ScenarioTemplate
from .hygiene_models import DormBinding, HygieneInspector, DormInspection


class StudentOnlyAdmin(admin.ModelAdmin):
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'user':
            from django.contrib.auth import get_user_model
            kwargs['queryset'] = get_user_model().objects.filter(accountprofile__role='student', is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(DormBinding)
class DormBindingAdmin(StudentOnlyAdmin):
    list_display = ('user', 'room', 'approved', 'updated_at')
    list_filter = ('approved', 'room__building')
    search_fields = ('user__username', 'room__building', 'room__room_number')
    readonly_fields = ('updated_at',)


@admin.register(HygieneInspector)
class HygieneInspectorAdmin(StudentOnlyAdmin):
    list_display = ('user', 'active')
    list_filter = ('active',)
    search_fields = ('user__username',)


@admin.register(DormInspection)
class DormInspectionAdmin(admin.ModelAdmin):
    list_display = ('room_label', 'inspected_on', 'inspector', 'score', 'passed', 'created_at')
    list_filter = ('passed', 'inspected_on', 'room__building')
    search_fields = ('room_label', 'inspector__username')
    readonly_fields = ('id', 'room', 'room_label', 'inspector', 'inspected_on', 'items', 'score', 'passed', 'created_at', 'evidence_links')
    exclude = ('submission_key',)

    @admin.display(description='逐项照片（需要登录）')
    def evidence_links(self, obj):
        from django.utils.html import format_html_join
        return format_html_join(' · ', '<a href="/api/v1/hygiene/photos/{}/" target="_blank" rel="noopener">{}</a>', ((p.id, p.item_key) for p in obj.evidence.all()))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScenarioTemplate)
class ScenarioTemplateAdmin(admin.ModelAdmin):
    list_display = ("icon", "name", "code", "category", "total_sla_display",
                    "reminder_lead_hours", "is_emergency", "sort_order", "is_active")
    list_filter = ("category", "is_emergency", "is_active", "is_demo")
    search_fields = ("name", "code", "summary")
    fieldsets = (
        ("场景定义", {"fields": ("code", "code_prefix", "name", "category", "icon", "color", "summary", "sort_order", "is_active", "is_demo")}),
        ("报备表单", {"fields": ("fields_schema",), "description": "JSON 数组，每项形如 {\"key\":\"hazard\",\"label\":\"隐患类型\",\"type\":\"select\",\"options\":[...],\"required\":true}"}),
        ("办理阶段", {"fields": ("stages",), "description": "JSON 数组，每项形如 {\"key\":\"submitted\",\"name\":\"待受理\",\"desc\":\"…\"}"}),
        ("时限与提醒", {"fields": ("accept_sla_hours", "handle_sla_hours", "reminder_lead_hours", "escalate_hours")}),
        ("控制项", {"fields": ("requires_photo", "requires_review", "is_emergency")}),
    )

    @admin.display(description="总时限")
    def total_sla_display(self, obj):
        return f"{obj.total_sla_hours} 小时"


class MatterEventInline(admin.TabularInline):
    model = MatterEvent
    extra = 0
    readonly_fields = ("kind", "from_status", "to_status", "note", "actor_name", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ReminderInline(admin.TabularInline):
    model = Reminder
    extra = 0
    fields = ("rule", "level", "title", "status", "triggered_at", "ack_name")
    readonly_fields = ("rule", "level", "title", "triggered_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HealthMatter)
class HealthMatterAdmin(admin.ModelAdmin):
    list_display = ("code", "template", "title", "location", "status_badge",
                    "priority", "overdue_badge", "due_at", "handler_name", "is_demo")
    list_filter = ("template", "status", "priority", "is_demo", "source", "submitted_at")
    search_fields = ("code", "title", "location", "detail", "reporter_name", "handler_name")
    readonly_fields = ("code", "id", "created_at", "updated_at", "accepted_at", "closed_at")
    date_hierarchy = "submitted_at"
    inlines = (MatterEventInline, ReminderInline)
    fieldsets = (
        ("报备信息", {"fields": ("code", "id", "template", "title", "location", "detail", "payload", "photo", "source")}),
        ("报备人", {"fields": ("reporter", "reporter_name", "reporter_contact")}),
        ("办理", {"fields": ("status", "priority", "handler", "handler_name", "accepted_at", "due_at", "closed_at")}),
        ("其他", {"fields": ("is_demo", "created_at", "updated_at")}),
    )
    actions = ("action_generate_reminders",)

    @admin.display(description="状态")
    def status_badge(self, obj):
        return obj.status_name

    @admin.display(description="超期", boolean=True)
    def overdue_badge(self, obj):
        return obj.is_overdue

    @admin.action(description="为选中事项立即巡检并生成自动提醒")
    def action_generate_reminders(self, request, queryset):
        from .services import generate_reminders
        created = generate_reminders(queryset=queryset.select_related("template"))
        self.message_user(request, f"已生成 {len(created)} 条自动提醒。")


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("triggered_at", "level", "rule", "title", "matter", "status", "ack_name", "ack_at")
    list_filter = ("level", "rule", "status", "triggered_at")
    search_fields = ("title", "body", "matter__code", "matter__title")
    readonly_fields = ("dedup_key", "created_at")
    autocomplete_fields = ("matter",)


@admin.register(MatterEvent)
class MatterEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "matter", "kind", "from_status", "to_status", "actor_name", "note")
    list_filter = ("kind", "created_at")
    search_fields = ("matter__code", "note", "actor_name")
    autocomplete_fields = ("matter",)
    readonly_fields = ("matter", "kind", "from_status", "to_status", "note", "actor", "actor_name", "created_at")


@admin.register(MapPoint)
class MapPointAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "status_badge", "map_position", "is_custom",
                    "last_done_at", "last_action_by", "updated_at")
    list_filter = ("status", "category", "is_custom", "is_demo")
    search_fields = ("name", "note", "source_ref")
    fieldsets = (
        ("点位信息", {"fields": ("name", "category", "note")}),
        ("位置（底图百分比 0-100）", {"fields": ("map_x", "map_y")}),
        ("处理状态", {"fields": ("status", "last_done_at", "last_action_by", "created_by_name")}),
        ("来源", {"fields": ("is_custom", "source_ref", "is_demo")}),
    )

    @admin.display(description="状态")
    def status_badge(self, obj):
        color = "#2f9e7f" if obj.status == "done" else "#d1443f"
        return format_html('<b style="color:{}">{}</b>', color, obj.get_status_display())

    @admin.display(description="坐标")
    def map_position(self, obj):
        return f"{obj.map_x:.1f}% / {obj.map_y:.1f}%"

