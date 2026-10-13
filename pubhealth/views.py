"""公共卫生管理平台 —— 页面与 API 视图。

权限边界（面向不同人群）：
    公众端（无需登录）
        /report/              报备与进度跟踪页
        /api/v1/scenarios/    场景模板（含报备字段定义）
        /api/v1/matters/      提交报备
        /api/v1/track/        凭编号查询本人事项进度
        /api/v1/matters/<编号>/  凭编号查看事项详情（编号不可枚举）
    管理端（需 staff 登录，未登录跳转登录页）
        /                     数据驾驶舱
        /api/v1/overview/     总览统计
        /api/v1/matters/list/ 全量事项台账
        /api/v1/reminders/    自动提醒清单 / 确认
        /api/v1/timeline/     全量办理流水
        /api/v1/map/points/…  消杀点位增删与状态标记
"""

import json
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from mosquito.views import PHOTO_CONTENT_TYPES, validate_photo

from . import services
from .models import OPEN_STATUSES, HealthMatter, MapPoint, Reminder, ScenarioTemplate


LOGIN_URL = "/account/"


def can_manage(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff)


def _safe_next(raw, fallback="/"):
    """只接受站内相对路径，避免登录后被跳到外部地址。"""
    raw = (raw or "").strip()
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return fallback


def login_redirect(request, next_url="/"):
    return redirect(f"{LOGIN_URL}?next={quote(_safe_next(next_url))}")


def _login_required_json(request):
    """管理端数据统一鉴权：未登录或非管理人员 → 403 并告知前端去登录。"""
    if can_manage(request.user):
        return None
    return JsonResponse({
        "message": "该数据仅对已登录的管理人员开放",
        "loginRequired": True,
        "loginUrl": f"{LOGIN_URL}?next={quote(_safe_next(request.get_full_path()))}",
    }, status=403)


def _page(name):
    html = (settings.BASE_DIR / "dist" / name).read_text(encoding="utf-8")
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@ensure_csrf_cookie
@require_GET
def home_page(request):
    return _page("home.html")


@ensure_csrf_cookie
@require_GET
def cockpit_page(request):
    """数据驾驶舱面向管理人员：访客一律先去登录，登录后自动回到驾驶舱。"""
    if not can_manage(request.user):
        return login_redirect(request, request.get_full_path() or "/")
    return _page("cockpit.html")


@ensure_csrf_cookie
@require_GET
def matter_page(request):
    return _page("matter.html")


# --------------------------------------------------------------------------- #
# 总览
# --------------------------------------------------------------------------- #
@require_GET
def overview(request):
    denied = _login_required_json(request)
    if denied:
        return denied
    services.generate_reminders()
    data = services.overview_stats()
    data["recentEvents"] = services.recent_events(20)
    data["period"] = services.period_summary(7)
    data["canManage"] = can_manage(request.user)
    data["authenticated"] = request.user.is_authenticated
    data["userName"] = request.user.get_username() if request.user.is_authenticated else ""
    return JsonResponse(data)


@require_GET
def scenario_list(request):
    services.generate_reminders()
    stats = {item["code"]: item for item in services.scenario_stats()}
    data = []
    for template in ScenarioTemplate.objects.filter(is_active=True):
        item = {
            "code": template.code,
            "name": template.name,
            "category": template.category,
            "categoryName": template.get_category_display(),
            "icon": template.icon,
            "color": template.color,
            "summary": template.summary,
            "isEmergency": template.is_emergency,
            "requiresPhoto": template.requires_photo,
            "requiresReview": template.requires_review,
            "slaHours": template.total_sla_hours,
            "acceptSlaHours": template.accept_sla_hours,
            "handleSlaHours": template.handle_sla_hours,
            "reminderLeadHours": template.reminder_lead_hours,
            "fields": template.field_list(),
            "stages": template.stage_list(),
        }
        item.update(stats.get(template.code, {}))
        data.append(item)
    return JsonResponse({"scenarios": data})


# --------------------------------------------------------------------------- #
# 事项
# --------------------------------------------------------------------------- #
@require_GET
def matter_list(request):
    denied = _login_required_json(request)
    if denied:
        return denied
    services.generate_reminders()
    queryset = HealthMatter.objects.select_related("template")
    template_code = request.GET.get("scenario", "").strip()
    if template_code and template_code != "all":
        queryset = queryset.filter(template__code=template_code)
    status = request.GET.get("status", "").strip()
    if status == "open":
        queryset = queryset.filter(status__in=OPEN_STATUSES)
    elif status == "overdue":
        queryset = queryset.filter(status__in=OPEN_STATUSES, due_at__lt=timezone.now())
    elif status in dict(HealthMatter.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    keyword = request.GET.get("q", "").strip()[:40]
    if keyword:
        from django.db.models import Q
        queryset = queryset.filter(Q(code__icontains=keyword) | Q(title__icontains=keyword)
                                   | Q(location__icontains=keyword) | Q(reporter_name__icontains=keyword))
    try:
        limit = max(1, min(200, int(request.GET.get("limit", "60"))))
    except (TypeError, ValueError):
        limit = 60
    items = [services.matter_brief(item) for item in queryset[:limit]]
    return JsonResponse({"count": len(items), "items": items})


def _validate_payload(template, payload):
    errors = []
    cleaned = {}
    schema = {field["key"]: field for field in template.field_list()}
    for key, field in schema.items():
        raw = payload.get(key, "")
        if isinstance(raw, str):
            raw = raw.strip()
        if field.get("required") and not raw:
            errors.append(f"请填写「{field['label']}」")
            continue
        if raw in (None, ""):
            continue
        if field.get("type") == "number":
            try:
                cleaned[key] = float(raw)
            except (TypeError, ValueError):
                errors.append(f"「{field['label']}」需填写数字")
                continue
        elif field.get("type") == "select" and field.get("options") and raw not in field["options"]:
            errors.append(f"「{field['label']}」选项无效")
            continue
        else:
            cleaned[key] = str(raw)[:200]
    return cleaned, errors


@require_http_methods(["POST"])
def matter_collection(request):
    photo = None
    if request.content_type.startswith("application/json"):
        if len(request.body) > 8192:
            return JsonResponse({"message": "提交内容过长"}, status=400)
        try:
            data = json.loads(request.body or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"message": "提交内容不是有效 JSON"}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({"message": "提交内容格式错误"}, status=400)
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        source = "web"
    elif request.content_type.startswith("multipart/form-data"):
        data = request.POST
        payload = {key[6:]: value for key, value in request.POST.items() if key.startswith("field_")}
        if set(request.FILES) - {"photo"} or len(request.FILES.getlist("photo")) > 1:
            return JsonResponse({"message": "每条报备只能上传一张现场照片"}, status=400)
        photo = request.FILES.get("photo")
        source = request.POST.get("source", "web")
    else:
        return JsonResponse({"message": "请求格式无效"}, status=400)

    template = ScenarioTemplate.objects.filter(code=str(data.get("template", "")).strip(), is_active=True).first()
    if template is None:
        return JsonResponse({"message": "请选择有效的公共卫生场景"}, status=400)

    title = str(data.get("title", "")).strip()
    location = str(data.get("location", "")).strip()
    detail = str(data.get("detail", "")).strip()
    reporter_name = str(data.get("reporter", data.get("reporterName", ""))).strip()
    reporter_contact = str(data.get("contact", data.get("reporterContact", ""))).strip()
    if not title or len(title) > 120:
        return JsonResponse({"message": "请填写120字以内的事项标题"}, status=400)
    if not location or len(location) > 100:
        return JsonResponse({"message": "请填写100字以内的发生地点"}, status=400)
    if len(detail) > 1000:
        return JsonResponse({"message": "情况描述不能超过1000字"}, status=400)
    if len(reporter_name) > 60 or len(reporter_contact) > 60:
        return JsonResponse({"message": "报备人或联系方式过长"}, status=400)

    cleaned, errors = _validate_payload(template, payload)
    if errors:
        return JsonResponse({"message": "；".join(errors[:3]), "errors": errors}, status=400)

    if template.requires_photo and not photo:
        return JsonResponse({"message": f"「{template.name}」需要上传现场照片"}, status=400)
    if photo:
        photo_error = validate_photo(photo)
        if photo_error:
            return JsonResponse({"message": photo_error}, status=400)

    matter = services.create_matter(
        template, title=title, location=location, detail=detail, payload=cleaned, photo=photo,
        reporter=request.user, reporter_name=reporter_name, reporter_contact=reporter_contact,
        source=source if source in dict(HealthMatter.SOURCE_CHOICES) else "web",
    )
    services.generate_reminders(queryset=HealthMatter.objects.filter(pk=matter.pk).select_related("template"))
    request.session['public_health_receipts'] = (request.session.get('public_health_receipts', []) + [str(matter.id)])[-100:]
    return JsonResponse({"message": "报备已提交", "matter": services.matter_detail(matter)}, status=201)


def _find_matter(identifier):
    queryset = HealthMatter.objects.select_related("template")
    if len(identifier) == 36 and identifier.count("-") == 4:
        return queryset.filter(id=identifier).first()
    return queryset.filter(code__iexact=identifier).first()


@require_GET
def matter_detail(request, identifier):
    services.generate_reminders()
    matter = _find_matter(identifier)
    if matter is None:
        return JsonResponse({"message": "未找到该事项，请核对编号"}, status=404)
    if not _may_read_matter(request, matter):
        return JsonResponse({'message': '请使用提交时的浏览器或本人登录账号查询，管理端可查询全量事项'}, status=403)
    return JsonResponse(services.matter_detail(matter))


def _may_read_matter(request, matter):
    return (can_manage(request.user) or str(matter.id) in request.session.get('public_health_receipts', [])
            or (request.user.is_authenticated and matter.reporter_id == request.user.pk))


@require_GET
def matter_track(request):
    code = request.GET.get("code", "").strip()
    if not code:
        return JsonResponse({"message": "请输入事项编号"}, status=400)
    services.generate_reminders()
    matter = _find_matter(code)
    if matter is None:
        return JsonResponse({"message": "未找到该编号对应的事项"}, status=404)
    if not _may_read_matter(request, matter):
        return JsonResponse({'message': '请使用提交时的浏览器或本人登录账号查询'}, status=403)
    return JsonResponse(services.matter_detail(matter))


@require_POST
def matter_advance(request, identifier):
    denied = _login_required_json(request)
    if denied:
        return denied
    matter = _find_matter(identifier)
    if matter is None:
        return JsonResponse({"message": "未找到该事项"}, status=404)
    try:
        body = json.loads(request.body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {}
    action = body.get("action") or request.POST.get("action")
    note = str(body.get("note") or request.POST.get("note") or "")
    if action == "note":
        services.add_note(matter, note or "更新进展", actor=request.user)
    elif action == "assign":
        handler_name = str(body.get("handler") or request.POST.get("handler") or "").strip()
        if not handler_name:
            return JsonResponse({"message": "请填写承办单位或人员"}, status=400)
        services.assign(matter, handler_name=handler_name, actor=request.user)
    elif action in dict(HealthMatter.STATUS_CHOICES):
        services.transition(matter, action, actor=request.user, note=note)
    else:
        return JsonResponse({"message": "无效操作"}, status=400)
    services.generate_reminders(queryset=HealthMatter.objects.filter(pk=matter.pk).select_related("template"))
    return JsonResponse({"message": "已更新办理进度", "matter": services.matter_detail(matter)})


@require_GET
def matter_photo(request, identifier):
    if not can_manage(request.user):
        raise PermissionDenied
    matter = _find_matter(identifier)
    if matter is None or not matter.photo:
        raise Http404
    try:
        photo_file = matter.photo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404 from None
    content_type = PHOTO_CONTENT_TYPES.get(Path(matter.photo.name).suffix.lower(), "application/octet-stream")
    response = FileResponse(photo_file, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    return response


# --------------------------------------------------------------------------- #
# 自动提醒
# --------------------------------------------------------------------------- #
@require_GET
def reminder_list(request):
    denied = _login_required_json(request)
    if denied:
        return denied
    services.generate_reminders()
    summary = services.reminder_summary()
    level = request.GET.get("level", "").strip()
    queryset = Reminder.objects.filter(status="pending").select_related("matter", "matter__template")
    if level in dict(Reminder.LEVEL_CHOICES):
        queryset = queryset.filter(level=level)
    summary["items"] = [services.reminder_brief(item) for item in queryset[:60]]
    summary["levels"] = [{"key": key, "name": name,
                          "value": Reminder.objects.filter(status="pending", level=key).count()}
                         for key, name in Reminder.LEVEL_CHOICES]
    return JsonResponse(summary)


@require_POST
def reminder_ack(request, reminder_id):
    denied = _login_required_json(request)
    if denied:
        return denied
    reminder = get_object_or_404(Reminder, pk=reminder_id)
    if reminder.status == "pending":
        services.ack_reminder(reminder, actor=request.user)
        services.add_note(reminder.matter, f"已确认系统提醒：{reminder.title}（{reminder.get_level_display()}）",
                          actor=request.user, kind="reminder")
    return JsonResponse({"message": "已确认", "id": reminder.id, "status": reminder.status})


@require_GET
def timeline(request):
    denied = _login_required_json(request)
    if denied:
        return denied
    return JsonResponse({"items": services.recent_events(int(request.GET.get("limit", "24") or 24))})


# --------------------------------------------------------------------------- #
# 地图点位：可自定义点位 + 已处理（绿）/ 未处理（红）
# --------------------------------------------------------------------------- #
def _point_payload(request):
    if request.content_type and request.content_type.startswith("application/json"):
        try:
            data = json.loads(request.body or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        return data if isinstance(data, dict) else {}
    return request.POST.dict()


@require_GET
def map_point_list(request):
    denied = _login_required_json(request)
    if denied:
        return denied
    from mosquito.models import CampusMap
    map_id = request.GET.get('map', 'default')
    queryset = services.map_point_queryset()
    if map_id == 'default':
        queryset = queryset.filter(campus_map__isnull=True)
    elif map_id.isdigit():
        queryset = queryset.filter(campus_map_id=int(map_id), campus_map__is_active=True)
    else:
        return JsonResponse({'message': '无效地图'}, status=400)
    points = list(queryset)
    maps = [{'id': 'default', 'name': '东莞校区原始底图', 'image': '/static/assets/gdmu-dongguan-campus-2025.jpg'}]
    maps += [{'id': str(m.pk), 'name': m.name, 'image': f'/maps/{m.pk}/image/'} for m in CampusMap.objects.filter(is_active=True).exclude(image='')]
    status = request.GET.get("status", "").strip()
    if status in dict(MapPoint.STATUS_CHOICES):
        points = [item for item in points if item.status == status]
    return JsonResponse({
        "stats": services.map_point_stats(points),
        "maps": maps,
        "categories": [{"key": key, "name": name} for key, name in MapPoint.CATEGORY_CHOICES],
        "points": [services.map_point_brief(item) for item in points],
    })


@require_POST
def map_point_collection(request):
    denied = _login_required_json(request)
    if denied:
        return denied
    data = _point_payload(request)
    from mosquito.models import CampusMap
    map_id = str(data.get('map', 'default'))
    campus_map = None
    if map_id != 'default':
        if not map_id.isdigit():
            return JsonResponse({'message': '无效地图'}, status=400)
        campus_map = get_object_or_404(CampusMap, pk=int(map_id), is_active=True)
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 60:
        return JsonResponse({"message": "请填写 60 字以内的点位名称"}, status=400)
    note = str(data.get("note", "")).strip()
    if len(note) > 180:
        return JsonResponse({"message": "点位说明请控制在 180 字以内"}, status=400)
    operator = str(data.get("operator", "")).strip()
    if len(operator) > 60:
        return JsonResponse({"message": "登记人名称过长"}, status=400)

    point = services.create_map_point(
        name=name,
        category=str(data.get("category", "other")),
        map_x=data.get("x", 50),
        map_y=data.get("y", 50),
        note=note,
        operator_name=operator or (request.user.get_username() if request.user.is_authenticated else ""),
        status=str(data.get("status", "pending")),
    )
    point.campus_map = campus_map
    point.save(update_fields=['campus_map'])
    return JsonResponse({
        "message": "自定义点位已保存，处理完成后可一键标记为已处理",
        "point": services.map_point_brief(point),
        "stats": services.map_point_stats(),
    }, status=201)


def _find_point(point_id):
    return MapPoint.objects.filter(pk=point_id).first()


@require_POST
def map_point_status(request, point_id):
    denied = _login_required_json(request)
    if denied:
        return denied
    point = _find_point(point_id)
    if point is None:
        return JsonResponse({"message": "点位不存在或已删除"}, status=404)
    data = _point_payload(request)
    status = str(data.get("status", "")).strip()
    if status not in dict(MapPoint.STATUS_CHOICES):
        return JsonResponse({"message": "无效的处理状态"}, status=400)
    services.set_map_point_status(
        point, status,
        operator_name=str(data.get("operator", "")).strip(),
        note=str(data.get("note", "")).strip(),
    )
    return JsonResponse({
        "message": f"「{point.name}」已标记为{point.get_status_display()}",
        "point": services.map_point_brief(point),
        "stats": services.map_point_stats(),
    })


@require_POST
def map_point_delete(request, point_id):
    denied = _login_required_json(request)
    if denied:
        return denied
    point = _find_point(point_id)
    if point is None:
        return JsonResponse({"message": "点位不存在或已删除"}, status=404)
    name = point.name
    point.delete()
    return JsonResponse({"message": f"点位「{name}」已删除", "stats": services.map_point_stats()})

