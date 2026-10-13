import json
import uuid
import warnings
from datetime import timedelta
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .models import AreaTreatment, CampusArea, CampusMap, DormCampaign, DormRecord, DormRoom, HazardReport


MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
PHOTO_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
PHOTO_CONTENT_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def validate_photo(upload):
    if upload.size == 0 or upload.size > MAX_PHOTO_BYTES:
        return "现场照片须在5MB以内"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                image_format = image.format
                if image_format not in PHOTO_EXTENSIONS or image.width * image.height > MAX_PHOTO_PIXELS:
                    return "请上传2000万像素以内的 JPG、PNG 或 WebP 图片"
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning):
        return "图片内容无效，请重新选择 JPG、PNG 或 WebP 图片"
    finally:
        upload.seek(0)
    upload.name = f"{uuid.uuid4().hex}{PHOTO_EXTENSIONS[image_format]}"
    return None


def report_json(report):
    return {
        "id": str(report.id),
        "location": report.location,
        "type": report.kind,
        "detail": report.detail,
        "hasPhoto": bool(report.photo),
        "status": report.status,
        "processingNote": report.processing_note,
        "createdAt": timezone.localtime(report.created_at).strftime("%Y-%m-%dT%H:%M"),
        "updatedAt": timezone.localtime(report.updated_at).strftime("%Y-%m-%dT%H:%M"),
        "isDemo": report.is_demo,
    }


@ensure_csrf_cookie
@require_GET
def public_page(request):
    html = (settings.BASE_DIR / "dist" / "dashboard.html").read_text(encoding="utf-8")
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@ensure_csrf_cookie
@require_GET
def report_page(request):
    html = (settings.BASE_DIR / "dist" / "dashboard.html").read_text(encoding="utf-8")
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@require_http_methods(["POST"])
def report_collection(request):
    photo = None
    if request.content_type.startswith("application/json"):
        if len(request.body) > 4096:
            return JsonResponse({"message": "请求格式无效"}, status=400)
        try:
            data = json.loads(request.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"message": "提交内容不是有效 JSON"}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({"message": "提交内容格式错误"}, status=400)
    elif request.content_type.startswith("multipart/form-data"):
        data = request.POST
        if set(request.FILES) - {"photo"} or len(request.FILES.getlist("photo")) > 1:
            return JsonResponse({"message": "每条线索只能上传一张现场照片"}, status=400)
        photo = request.FILES.get("photo")
    else:
        return JsonResponse({"message": "请求格式无效"}, status=400)

    location = data.get("location")
    kind = data.get("type")
    detail = data.get("detail", "")
    if not isinstance(location, str) or not location.strip() or len(location.strip()) > 80:
        return JsonResponse({"message": "请填写80字以内的发现位置"}, status=400)
    if kind not in dict(HazardReport.KIND_CHOICES):
        return JsonResponse({"message": "请选择有效的隐患类型"}, status=400)
    if not isinstance(detail, str) or len(detail.strip()) > 200:
        return JsonResponse({"message": "补充说明不能超过200字"}, status=400)
    if photo:
        photo_error = validate_photo(photo)
        if photo_error:
            return JsonResponse({"message": photo_error}, status=400)

    report = HazardReport.objects.create(location=location.strip(), kind=kind, detail=detail.strip(), photo=photo)
    return JsonResponse(report_json(report), status=201)


@staff_member_required
@require_GET
def report_photo(request, report_id):
    if not request.user.has_perm("mosquito.view_hazardreport"):
        raise PermissionDenied
    report = get_object_or_404(HazardReport, id=report_id)
    if not report.photo:
        raise Http404
    try:
        photo_file = report.photo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404 from None
    content_type = PHOTO_CONTENT_TYPES.get(Path(report.photo.name).suffix.lower(), "application/octet-stream")
    response = FileResponse(photo_file, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def report_detail(request, report_id):
    try:
        report = HazardReport.objects.get(id=report_id)
    except HazardReport.DoesNotExist:
        return JsonResponse({"message": "未找到该线索"}, status=404)
    return JsonResponse(report_json(report))


@require_GET
def campus_areas(request):
    areas = CampusArea.objects.filter(is_active=True).prefetch_related("treatments")
    map_id = request.GET.get("map", "default")
    if map_id == "default":
        areas = areas.filter(campus_map__isnull=True)
    elif map_id.isdigit():
        areas = areas.filter(campus_map_id=int(map_id))
    else:
        return JsonResponse({"message": "无效地图"}, status=400)
    today = timezone.localdate()
    items = []
    for area in areas:
        records = list(area.treatments.all())
        latest = records[0] if records else None
        last_date = timezone.localtime(latest.treated_at).date() if latest else None
        next_date = last_date + timedelta(days=area.interval_days) if last_date else None
        status = "unrecorded" if latest is None else ("due" if next_date <= today else "current")
        items.append({
            "id": area.id,
            "name": area.name,
            "category": area.get_category_display(),
            "mapX": area.map_x,
            "mapY": area.map_y,
            "intervalDays": area.interval_days,
            "status": status,
            "lastTreatedOn": last_date.isoformat() if last_date else None,
            "nextDueOn": next_date.isoformat() if next_date else None,
            "lastMethod": latest.get_method_display() if latest else None,
            "note": area.note,
            "isDemo": area.is_demo,
            "history": [
                {"date": timezone.localtime(item.treated_at).strftime("%Y-%m-%d %H:%M"),
                 "method": item.get_method_display(), "operator": item.operator, "note": item.note}
                for item in records[:5]
            ],
        })
    maps = [{"id": "default", "name": "东莞校区 · 原始底图", "image": "/static/assets/gdmu-dongguan-campus-2025.jpg"}]
    maps += [{"id": str(m.id), "name": m.name, "image": f"/maps/{m.id}/image/" if m.image else maps[0]["image"]}
             for m in CampusMap.objects.filter(is_active=True)]
    return JsonResponse({"campus": "广东医科大学东莞校区", "areas": items, "maps": maps, "isSchematic": True})


def active_campaign():
    today = timezone.localdate()
    return DormCampaign.objects.filter(is_active=True, starts_on__lte=today, ends_on__gte=today).first()


@require_GET
def dorm_rooms(request):
    campaign = active_campaign()
    rooms = list(DormRoom.objects.filter(is_active=True))
    states = {room.id: {"pickedUp": False, "treated": False, "lastPickupOn": None, "lastTreatmentOn": None} for room in rooms}
    total_quantity = 0
    pending_count = 0
    if campaign:
        records = DormRecord.objects.filter(campaign=campaign, room__in=rooms).order_by("-created_at")
        for record in records:
            if record.status == "pending":
                pending_count += 1
                continue
            if record.status != "verified":
                continue
            state = states[record.room_id]
            recorded_on = timezone.localtime(record.created_at).date().isoformat()
            if record.kind == "pickup":
                state["pickedUp"] = True
                state["lastPickupOn"] = state["lastPickupOn"] or recorded_on
                total_quantity += record.quantity
            elif record.kind == "treatment":
                state["treated"] = True
                state["lastTreatmentOn"] = state["lastTreatmentOn"] or recorded_on
    items = [{"id": room.id, "building": room.building, "number": room.room_number,
              "isDemo": room.is_demo, **states[room.id]} for room in rooms]
    picked_up = sum(item["pickedUp"] for item in items)
    treated = sum(item["treated"] for item in items)
    return JsonResponse({
        "campaign": ({"id": campaign.id, "name": campaign.name, "isDemo": campaign.is_demo} if campaign else None),
        "rooms": items,
        "totals": {"rooms": len(items), "pickedUp": picked_up, "notPickedUp": len(items) - picked_up,
                   "treated": treated, "notTreated": len(items) - treated,
                   "tablets": total_quantity, "pending": pending_count},
    })


def dorm_receipt_json(record):
    return {
        "id": str(record.id),
        "room": str(record.room),
        "kind": record.kind,
        "status": record.status,
        "reviewNote": record.review_note,
        "hasPhoto": bool(record.photo),
        "createdAt": timezone.localtime(record.created_at).strftime("%Y-%m-%d %H:%M"),
    }


@require_http_methods(["POST"])
def dorm_record_collection(request):
    if not request.user.is_authenticated:
        return JsonResponse({"message": "请先通过页面顶部登录 / 注册入口登录，再提交宿舍登记"}, status=401)
    if not request.content_type.startswith("multipart/form-data"):
        return JsonResponse({"message": "请使用表单提交"}, status=400)
    campaign = active_campaign()
    if campaign is None:
        return JsonResponse({"message": "当前没有开放的宿舍登记批次"}, status=400)
    if set(request.FILES) - {"photo"} or len(request.FILES.getlist("photo")) > 1:
        return JsonResponse({"message": "每次只能上传一张凭证照片"}, status=400)
    try:
        room = DormRoom.objects.get(id=int(request.POST.get("room", "")), is_active=True)
    except (ValueError, TypeError, DormRoom.DoesNotExist):
        return JsonResponse({"message": "请选择有效的宿舍房间"}, status=400)
    kind = request.POST.get("kind", "")
    if kind not in dict(DormRecord.KIND_CHOICES):
        return JsonResponse({"message": "请选择登记类型"}, status=400)
    note = request.POST.get("note", "").strip()
    if len(note) > 200:
        return JsonResponse({"message": "备注不能超过200字"}, status=400)
    method = request.POST.get("method", "") if kind == "treatment" else ""
    if kind == "treatment" and method not in dict(DormRecord.METHOD_CHOICES):
        return JsonResponse({"message": "请选择经学校允许的处理方式"}, status=400)
    try:
        quantity = int(request.POST.get("quantity", "1")) if kind == "pickup" else 1
    except (ValueError, TypeError):
        return JsonResponse({"message": "领取数量须为1到20"}, status=400)
    if not 1 <= quantity <= 20:
        return JsonResponse({"message": "领取数量须为1到20"}, status=400)
    photo = request.FILES.get("photo")
    if kind == "treatment" and not photo:
        return JsonResponse({"message": "宿舍处理记录请上传现场凭证照片"}, status=400)
    if photo:
        photo_error = validate_photo(photo)
        if photo_error:
            return JsonResponse({"message": photo_error}, status=400)
    record = DormRecord.objects.create(
        campaign=campaign, room=room, kind=kind, method=method,
        quantity=quantity, photo=photo, note=note, submitted_by=request.user,
    )
    return JsonResponse(dorm_receipt_json(record), status=201)


@require_GET
def dorm_record_detail(request, record_id):
    record = get_object_or_404(DormRecord.objects.select_related("room"), id=record_id)
    return JsonResponse(dorm_receipt_json(record))


@staff_member_required
@require_GET
def dorm_record_photo(request, record_id):
    if not request.user.has_perm("mosquito.view_dormrecord"):
        raise PermissionDenied
    record = get_object_or_404(DormRecord, id=record_id)
    if not record.photo:
        raise Http404
    try:
        photo_file = record.photo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404 from None
    content_type = PHOTO_CONTENT_TYPES.get(Path(record.photo.name).suffix.lower(), "application/octet-stream")
    response = FileResponse(photo_file, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "service": "campus-mosquito-demo"})
