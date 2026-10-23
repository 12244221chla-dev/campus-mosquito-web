import json
import re
import uuid
from datetime import date
from django.db import transaction, IntegrityError
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from mosquito.models import AccountProfile, DormRoom
from mosquito.views import validate_photo, PHOTO_CONTENT_TYPES
from .hygiene_models import DormBinding, HygieneInspector, DormInspection, HygieneEvidence

RULES = [('floor', '地面卫生'), ('bed', '床铺整理'), ('desk', '桌面及物品摆放'), ('waste', '垃圾清理'), ('wash', '卫生间及洗漱区')]


def student(user):
    return user.is_authenticated and user.is_active and AccountProfile.objects.filter(user=user, role='student').exists()


def inspector(user):
    return student(user) and HygieneInspector.objects.filter(user=user, active=True).exists()


def manager(user):
    return user.is_authenticated and user.is_active and user.is_staff


def error(message, status=400):
    return JsonResponse({'message': message}, status=status)


def body(request):
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError
    return data


@require_GET
def home(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return error('请先在“我的”登录学生账号', 403)
    binding = DormBinding.objects.select_related('room').filter(user=request.user).first()
    can_inspect = inspector(request.user)
    is_manager = manager(request.user)
    records = DormInspection.objects.select_related('room', 'inspector')
    if not is_manager:
        from django.db.models import Q
        allowed = Q(inspector=request.user)
        if student(request.user) and binding and binding.approved:
            allowed |= Q(room=binding.room)
        records = records.filter(allowed)
    return JsonResponse({
        'canInspect': can_inspect, 'isStudent': student(request.user), 'canManage': is_manager,
        'rules': [{'key': key, 'label': label, 'max': 20} for key, label in RULES],
        'binding': {'roomId': binding.room_id, 'label': str(binding.room), 'approved': binding.approved} if binding else None,
        'rooms': [{'id': r.pk, 'label': str(r)} for r in DormRoom.objects.filter(is_active=True)] if student(request.user) else [],
        'records': [{'id': str(r.id), 'room': r.room_label, 'date': str(r.inspected_on), 'score': r.score, 'passed': r.passed} for r in records[:100]],
        'storageNotice': '演示环境：照片使用现有服务器存储，可能随重启或部署丢失，请勿上传真实宿舍隐私照片。',
    })


@require_POST
def bind_room(request):
    if not student(request.user):
        return error('仅学生账号可以申请宿舍绑定', 403)
    try:
        data = body(request)
        room = DormRoom.objects.get(pk=int(data.get('roomId')), is_active=True)
    except (ValueError, TypeError, DormRoom.DoesNotExist):
        return error('请选择已登记的宿舍')
    with transaction.atomic():
        binding, created = DormBinding.objects.select_for_update().get_or_create(user=request.user, defaults={'room': room})
        if not created and binding.room_id != room.pk:
            binding.room = room
            binding.approved = False
            binding.save()
    return JsonResponse({'message': '申请已保存，等待管理员确认' if not binding.approved else '该宿舍已确认'})


@require_POST
def upload_evidence(request):
    if not inspector(request.user):
        return error('此学生账号尚未获得检查评分授权', 403)
    key = request.POST.get('itemKey')
    if key not in dict(RULES):
        return error('检查项目无效')
    photo = request.FILES.get('photo')
    if not photo:
        return error('请上传照片')
    message = validate_photo(photo)
    if message:
        return error(message)
    evidence = HygieneEvidence.objects.create(owner=request.user, item_key=key, photo=photo)
    return JsonResponse({'id': str(evidence.id)}, status=201)


@require_POST
def create(request):
    if not inspector(request.user):
        return error('此学生账号尚未获得检查评分授权', 403)
    try:
        data = body(request)
        token = data.get('submissionKey', '')
        if not isinstance(token, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,64}', token):
            raise ValueError
        existing = DormInspection.objects.filter(submission_key=token).first()
        if existing:
            if existing.inspector_id != request.user.pk:
                return error('提交标识冲突', 409)
            return JsonResponse({'id': str(existing.id), 'score': existing.score})
        room = DormRoom.objects.get(pk=int(data.get('roomId')), is_active=True)
        checked_on = date.fromisoformat(data.get('date', ''))
        if checked_on > timezone.localdate():
            raise ValueError
        items = data.get('items')
        if not isinstance(items, list) or len(items) != 5:
            raise ValueError
        if {i.get('key') for i in items if isinstance(i, dict)} != set(dict(RULES)):
            raise ValueError
        cleaned, ids = [], []
        for key, label in RULES:
            item = next(i for i in items if i['key'] == key)
            deduction = item.get('deduction')
            if type(deduction) is not int or not 0 <= deduction <= 20:
                raise ValueError
            reason = item.get('reason', '')
            if not isinstance(reason, str) or len(reason.strip()) > 300:
                raise ValueError
            reason = reason.strip()
            photo_id = None
            if deduction:
                if not reason:
                    return error(label + '：扣分必须填写原因并附照片')
                photo_id = uuid.UUID(str(item.get('evidenceId', '')))
                ids.append(photo_id)
            cleaned.append({'key': key, 'label': label, 'deduction': deduction, 'reason': reason, 'evidenceId': str(photo_id) if photo_id else None})
    except (ValueError, TypeError, KeyError, StopIteration, DormRoom.DoesNotExist):
        return error('请检查宿舍、日期及五项扣分（每项须为0—20的整数）')
    try:
        with transaction.atomic():
            photos = list(HygieneEvidence.objects.select_for_update().filter(id__in=ids, owner=request.user, inspection__isnull=True))
            photo_map = {str(p.id): p for p in photos}
            if len(photos) != len(ids) or any(i['evidenceId'] and (i['evidenceId'] not in photo_map or photo_map[i['evidenceId']].item_key != i['key']) for i in cleaned):
                return error('照片无效、已使用或不属于本次检查人员，请重新选择')
            score = 100 - sum(i['deduction'] for i in cleaned)
            record = DormInspection.objects.create(submission_key=token, room=room, room_label=str(room), inspector=request.user, inspected_on=checked_on, items=cleaned, score=score, passed=score >= 80)
            HygieneEvidence.objects.filter(id__in=ids).update(inspection=record)
    except IntegrityError:
        record = DormInspection.objects.filter(submission_key=token, inspector=request.user).first()
        if not record:
            return error('提交冲突，请刷新检查记录后核对', 409)
    return JsonResponse({'id': str(record.id), 'score': record.score}, status=201)


def can_view(user, record):
    return manager(user) or (user.is_authenticated and user.is_active and (record.inspector_id == user.pk or (student(user) and DormBinding.objects.filter(user=user, room=record.room, approved=True).exists())))


@require_GET
def detail(request, identifier):
    record = get_object_or_404(DormInspection.objects.select_related('inspector'), pk=identifier)
    if not can_view(request.user, record):
        return error('无权查看该宿舍记录', 403)
    return JsonResponse({'id': str(record.id), 'room': record.room_label, 'date': str(record.inspected_on), 'createdAt': timezone.localtime(record.created_at).strftime('%Y-%m-%d %H:%M'), 'inspector': record.inspector.first_name or record.inspector.get_username(), 'score': record.score, 'passed': record.passed, 'items': record.items})


@require_GET
def photo(request, identifier):
    evidence = get_object_or_404(HygieneEvidence.objects.select_related('inspection'), pk=identifier)
    if not evidence.inspection or not can_view(request.user, evidence.inspection):
        return error('无权查看该照片', 403)
    try:
        handle = evidence.photo.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('照片暂不可用，演示环境文件可能已丢失')
    from pathlib import Path
    response = FileResponse(handle, content_type=PHOTO_CONTENT_TYPES.get(Path(evidence.photo.name).suffix, 'application/octet-stream'))
    response['Cache-Control'] = 'private, no-store'
    return response
