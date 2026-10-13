"""原生小程序使用现有 Django 会话与 CSRF，不接受客户端指定管理权限。"""
import json

from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST

from mosquito.portal import RegistrationForm, can_manage


def state(request):
    return {'csrfToken': get_token(request), 'authenticated': request.user.is_authenticated,
            'canManage': can_manage(request.user),
            'name': request.user.get_username() if request.user.is_authenticated else ''}


@require_GET
def session(request):
    return JsonResponse(state(request))


@require_POST
def account(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'message': '无效请求'}, status=400)
    if data.get('action') == 'register':
        form = RegistrationForm(data)
        if not form.is_valid():
            return JsonResponse({'message': '；'.join(str(e) for errors in form.errors.values() for e in errors)}, status=400)
        from mosquito.models import AccountProfile
        with transaction.atomic():
            user = get_user_model().objects.create_user(username=form.cleaned_data['username'],
                password=form.cleaned_data['password'], first_name=form.cleaned_data['name'])
            AccountProfile.objects.create(user=user, role=form.cleaned_data['role'], identifier=form.cleaned_data['identifier'].strip())
        login(request, user)
        return JsonResponse(state(request), status=201)
    role = data.get('role')
    if role not in ('student', 'teacher', 'manager'):
        return JsonResponse({'message': '请选择登录身份'}, status=400)
    identifier = str(data.get('identifier', '')).strip()
    username = identifier if role == 'manager' else f'{role}:{identifier}'
    user = authenticate(request, username=username, password=data.get('password', ''))
    if not user or (role == 'manager' and not can_manage(user)):
        return JsonResponse({'message': '账号、身份或密码不正确'}, status=400)
    login(request, user)
    return JsonResponse(state(request))


@require_POST
def signout(request):
    logout(request)
    return JsonResponse(state(request))
