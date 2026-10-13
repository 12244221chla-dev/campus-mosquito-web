import re

from django import forms
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import CampusMap, CampusArea, AreaTreatment, DormRoom, DormCampaign, DormRecord, AccountProfile
from .views import validate_photo


def can_manage(user):
    return user.is_authenticated and user.is_active and user.is_staff


def session_info(request):
    return JsonResponse({"authenticated": request.user.is_authenticated, "canManage": can_manage(request.user),
                         "name": request.user.get_username() if request.user.is_authenticated else ""})


class RegistrationForm(forms.Form):
    role = forms.ChoiceField(label="注册身份", choices=[("student", "学生端"), ("teacher", "教师端")])
    identifier = forms.CharField(label="学生学号 / 教师手机号", max_length=32)
    name = forms.CharField(label="姓名", max_length=80)
    password = forms.CharField(label="密码", widget=forms.PasswordInput)
    confirm = forms.CharField(label="确认密码", widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        identifier = data.get("identifier", "").strip()
        role = data.get("role")
        if role == "teacher" and not re.fullmatch(r"1[3-9]\d{9}", identifier):
            self.add_error("identifier", "请填写11位教师手机号")
        if role == "student" and not re.fullmatch(r"[A-Za-z0-9_-]{4,32}", identifier):
            self.add_error("identifier", "学号须为4至32位字母、数字或下划线")
        username = f"{role}:{identifier}"
        if get_user_model().objects.filter(username=username).exists():
            self.add_error("identifier", "该身份账号已注册")
        if data.get("password") != data.get("confirm"):
            self.add_error("confirm", "两次密码不一致")
        try:
            validate_password(data.get("password", ""), get_user_model()(username=username, first_name=data.get("name", "")))
        except ValidationError as error:
            self.add_error("password", error)
        data["username"] = username
        return data


def _safe_next(raw, fallback):
    """只接受站内相对路径，避免登录后被跳到外部地址。"""
    raw = (raw or "").strip()
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return fallback


# 仅管理人员可进入的入口；非管理人员被指向这些地址时改去报备页，避免登录来回跳
MANAGER_ONLY_PREFIXES = ("/admin", "/manage", "/api/v1/overview", "/api/v1/matters/list",
                         "/api/v1/reminders", "/api/v1/timeline", "/api/v1/map", "/cockpit")


def _landing_for(user, target):
    if can_manage(user):
        return target
    if target == "/" or target.startswith(MANAGER_ONLY_PREFIXES):
        return "/report/"
    return target


def account_page(request):
    registering = request.GET.get("mode") == "register"
    form = RegistrationForm(request.POST or None) if registering else None
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    error = ""
    if request.method == "POST":
        if registering and form.is_valid():
            user = get_user_model().objects.create_user(username=form.cleaned_data["username"],
                password=form.cleaned_data["password"], first_name=form.cleaned_data["name"])
            AccountProfile.objects.create(user=user, role=form.cleaned_data["role"], identifier=form.cleaned_data["identifier"].strip())
            login(request, user)
            return redirect("/report/")
        if not registering:
            role = request.POST.get("role", "student")
            identifier = request.POST.get("identifier", "").strip()
            username = identifier if role == "manager" else f"{role}:{identifier}"
            user = authenticate(request, username=username, password=request.POST.get("password", ""))
            if user and (role != "manager" or can_manage(user)):
                login(request, user)
                fallback = "/cockpit/" if can_manage(user) else "/"
                return redirect(_landing_for(user, _safe_next(next_url, fallback)))
            error = "账号、身份或密码不正确"
    return render(request, "mosquito/account.html", {"registering": registering, "form": form,
                                                     "error": error, "next": next_url,
                                                     "manager_entry": request.GET.get('entry') == 'manager' or next_url.startswith('/cockpit')})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("/")


class PhotoForm(forms.ModelForm):
    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "size"):
            error = validate_photo(image)
            if error:
                raise forms.ValidationError(error)
        return image


class MapForm(PhotoForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].required = not bool(self.instance.pk and self.instance.image)

    class Meta:
        model = CampusMap
        fields = ["name", "image", "is_active"]


class AreaForm(forms.ModelForm):
    class Meta:
        model = CampusArea
        fields = ["campus_map", "name", "category", "map_x", "map_y", "interval_days", "note", "is_active", "is_demo"]


class TreatmentForm(forms.ModelForm):
    class Meta:
        model = AreaTreatment
        fields = ["area", "method", "treated_at", "operator", "note", "is_demo"]
        widgets = {"treated_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}


class RoomsForm(forms.Form):
    building = forms.CharField(label="楼栋名称", max_length=40, help_text="例如8栋、9栋、10栋；不限楼栋数量")
    numbers = forms.CharField(label="房号清单", widget=forms.Textarea, help_text="每行一个房号，或用逗号分隔；不会覆盖已有房间")
    is_demo = forms.BooleanField(label="演示房间", required=False, initial=True)

    def clean_numbers(self):
        numbers = list(dict.fromkeys(re.split(r"[\s,，]+", self.cleaned_data["numbers"].strip())))
        if not 1 <= len(numbers) <= 500 or any(not re.fullmatch(r"[A-Za-z0-9-]{1,20}", n) for n in numbers):
            raise forms.ValidationError("一次最多500个房号，只支持字母、数字及短横线")
        return numbers


class CampaignForm(forms.ModelForm):
    class Meta:
        model = DormCampaign
        fields = ["name", "starts_on", "ends_on", "is_active", "is_demo"]
        widgets = {key: forms.DateInput(attrs={"type": "date"}) for key in ["starts_on", "ends_on"]}

    def clean(self):
        data = super().clean()
        if data.get("starts_on") and data.get("ends_on") and data["ends_on"] < data["starts_on"]:
            self.add_error("ends_on", "结束日期不能早于开始日期")
        return data


FORM_TYPES = {"map": (MapForm, "添加地图"), "area": (AreaForm, "编辑地图点位"),
              "treatment": (TreatmentForm, "登记区域消杀"), "rooms": (RoomsForm, "添加楼栋与房间"),
              "campaign": (CampaignForm, "创建领取批次")}


def manage(request):
    if not request.user.is_authenticated:
        return redirect("/account/?entry=manager&next=/manage/")
    if not can_manage(request.user):
        return render(request, "mosquito/denied.html", status=403)
    action = request.GET.get("action", "area")
    form_type, title = FORM_TYPES.get(action, FORM_TYPES["area"])
    instance = None
    if action in ("area", "map") and request.GET.get("id"):
        instance = get_object_or_404(CampusArea if action == "area" else CampusMap, pk=request.GET["id"])
    model_name = {"area": "campusarea", "map": "campusmap", "treatment": "areatreatment", "rooms": "dormroom", "campaign": "dormcampaign"}.get(action, "campusarea")
    if not request.user.has_perm(f"mosquito.{'change' if instance else 'add'}_{model_name}"):
        return render(request, "mosquito/denied.html", status=403)
    kwargs = {"instance": instance} if action != "rooms" else {}
    initial = {"area": request.GET.get("area")} if action == "treatment" else {}
    form = form_type(request.POST or None, request.FILES or None, initial=initial, **kwargs)
    saved = request.GET.get("saved") == "1"
    if request.method == "POST" and form.is_valid():
        if action == "rooms":
            for number in form.cleaned_data["numbers"]:
                DormRoom.objects.get_or_create(building=form.cleaned_data["building"].strip(), room_number=number,
                    defaults={"is_demo": form.cleaned_data["is_demo"]})
        else:
            obj = form.save(commit=False)
            if action == "treatment":
                obj.recorded_by = request.user
            obj.save()
        return redirect(f"/manage/?action={action}&saved=1")
    return render(request, "mosquito/manage.html", {"form": form, "title": title, "action": action,
        "saved": saved, "areas": CampusArea.objects.all(), "maps": CampusMap.objects.filter(is_active=True),
        "pending": DormRecord.objects.filter(status="pending").select_related("room")[:100],
        "buildings": DormRoom.objects.values_list("building", flat=True).distinct()})


@require_POST
def review_record(request, record_id):
    if not can_manage(request.user) or not request.user.has_perm("mosquito.change_dormrecord"):
        return JsonResponse({"message": "无核对权限"}, status=403)
    record = get_object_or_404(DormRecord, pk=record_id)
    status = request.POST.get("status")
    if status not in ("verified", "rejected"):
        return JsonResponse({"message": "无效状态"}, status=400)
    record.status = status
    record.review_note = f"{request.user.get_username()} · {timezone.localtime():%Y-%m-%d %H:%M} · {request.POST.get('note', '')}"[:200]
    record.save()
    return redirect("/manage/#review")


def map_image(request, map_id):
    campus_map = get_object_or_404(CampusMap, pk=map_id, is_active=True)
    if not campus_map.image:
        raise Http404
    try:
        return FileResponse(campus_map.image.open("rb"))
    except OSError:
        raise Http404 from None
