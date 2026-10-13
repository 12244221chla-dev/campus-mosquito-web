"""公共卫生事项引擎服务层。

集中实现可复用的四段能力：
    线上报备 create_matter → 进度跟踪 transition/assign/add_note → 自动提醒 generate_reminders → 数据统计 overview_stats
"""

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import (OPEN_STATUSES, STATUS_ORDER, HealthMatter, MapPoint, MatterEvent, Reminder,
                     ScenarioTemplate)


# --------------------------------------------------------------------------- #
# 线上报备
# --------------------------------------------------------------------------- #
def generate_trace_code(template, when=None):
    """生成可读事项编号，例如 WZ-20261012-0007。"""
    stamp = timezone.localtime(when or timezone.now()).strftime("%Y%m%d")
    prefix = f"{template.code_prefix}-{stamp}"
    seq = HealthMatter.objects.filter(code__startswith=prefix).count() + 1
    while HealthMatter.objects.filter(code=f"{prefix}-{seq:04d}").exists():
        seq += 1
    return f"{prefix}-{seq:04d}"


def compute_due_at(template, submitted_at):
    return submitted_at + timedelta(hours=template.total_sla_hours)


def create_matter(template, *, title, location, detail="", payload=None, photo=None,
                  reporter=None, reporter_name="", reporter_contact="", source="web",
                  priority=None, submitted_at=None, is_demo=False, actor_name=""):
    """创建一条报备事项，写入编号、到期时间，并落下第一条可追溯流水。"""
    submitted_at = submitted_at or timezone.now()
    if priority is None:
        priority = "urgent" if template.is_emergency else "normal"
    matter = HealthMatter.objects.create(
        code=generate_trace_code(template, submitted_at),
        template=template,
        title=title.strip()[:120],
        location=location.strip()[:100],
        detail=(detail or "").strip(),
        payload=payload or {},
        photo=photo or "",
        status="submitted",
        priority=priority,
        source=source,
        reporter=reporter if getattr(reporter, "is_authenticated", False) else None,
        reporter_name=(reporter_name or "").strip()[:60],
        reporter_contact=(reporter_contact or "").strip()[:60],
        is_demo=is_demo,
        submitted_at=submitted_at,
        due_at=compute_due_at(template, submitted_at),
    )
    MatterEvent.objects.create(
        matter=matter, kind="created", to_status="submitted",
        note="线上报备提交，系统自动生成编号与处置时限",
        actor=matter.reporter, actor_name=actor_name or matter.reporter_name or "报备人",
        created_at=submitted_at,
    )
    return matter


# --------------------------------------------------------------------------- #
# 进度跟踪
# --------------------------------------------------------------------------- #
def _actor_label(actor, fallback=""):
    if actor is not None and getattr(actor, "is_authenticated", False):
        return actor.get_username()[:60]
    return (fallback or "")[:60]


def transition(matter, to_status, *, actor=None, actor_name="", note="", kind=None, occurred_at=None):
    """推进事项状态，并写入不可篡改的办理流水。"""
    if to_status not in dict(HealthMatter.STATUS_CHOICES):
        raise ValueError(f"未知状态：{to_status}")
    now = occurred_at or timezone.now()
    from_status = matter.status
    matter.status = to_status
    if to_status == "accepted" and not matter.accepted_at:
        matter.accepted_at = now
    if to_status == "done":
        matter.closed_at = now
    if to_status == "rejected":
        matter.closed_at = now
    matter.save()
    MatterEvent.objects.create(
        matter=matter, kind=kind or ("review" if to_status == "done" else "status"),
        from_status=from_status, to_status=to_status,
        note=note[:300], actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_name=_actor_label(actor, actor_name), created_at=now,
    )
    if to_status in ("done", "rejected"):
        close_reminders(matter)
    return matter


def assign(matter, *, handler=None, handler_name="", actor=None, actor_name="", note=""):
    matter.handler = handler if getattr(handler, "is_authenticated", False) else None
    matter.handler_name = (handler_name or "").strip()[:80]
    matter.save(update_fields=["handler", "handler_name", "updated_at"])
    MatterEvent.objects.create(
        matter=matter, kind="assign", note=(note or f"分派给 {matter.handler_name or '承办单位'}")[:300],
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_name=_actor_label(actor, actor_name),
    )
    return matter


def add_note(matter, note, *, actor=None, actor_name="", kind="note"):
    event = MatterEvent.objects.create(
        matter=matter, kind=kind, note=note.strip()[:300],
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_name=_actor_label(actor, actor_name),
    )
    matter.save(update_fields=["updated_at"])
    return event


# --------------------------------------------------------------------------- #
# 自动提醒
# --------------------------------------------------------------------------- #
def _ensure_reminder(matter, rule, level, title, body, base_time, now):
    bucket = timezone.localtime(base_time).strftime("%Y-%m-%d")
    dedup_key = f"{matter.code}|{rule}|{level}|{bucket}"
    if Reminder.objects.filter(dedup_key=dedup_key).exists():
        return None
    reminder = Reminder.objects.create(
        matter=matter, rule=rule, level=level, title=title, body=body,
        dedup_key=dedup_key, status="pending", due_at=base_time, triggered_at=now,
        sent_at=now,
    )
    MatterEvent.objects.create(
        matter=matter, kind="reminder",
        note=f"[自动提醒·{reminder.get_level_display()}] {title}",
        actor_name="系统", created_at=now,
    )
    return reminder


def generate_reminders(now=None, queryset=None):
    """扫描在办事项，按模板时限规则生成提醒（幂等，可反复调用）。

    规则：
      accept_sla  报备后超过受理时限仍未受理        → 临期 / 升级
      due_soon    距处置到期不足 reminder_lead 小时  → 临期
      overdue     已过处置到期时间                  → 超期
      escalated   超期超过 escalate_hours           → 升级
    """
    now = now or timezone.now()
    matters = queryset if queryset is not None else HealthMatter.objects.select_related("template")
    created = []
    for matter in matters:
        if not matter.is_open:
            continue
        tpl = matter.template
        if matter.status == "submitted":
            accept_deadline = matter.submitted_at + timedelta(hours=tpl.accept_sla_hours)
            if now > accept_deadline:
                escalated = now > accept_deadline + timedelta(hours=tpl.escalate_hours)
                created.append(_ensure_reminder(
                    matter, "accept_sla", "escalate" if escalated else "warn",
                    f"{matter.code} 受理超时：{matter.title}",
                    f"已超过受理时限 {tpl.accept_sla_hours} 小时，请尽快受理。",
                    accept_deadline, now,
                ))
        if matter.due_at:
            lead = timedelta(hours=tpl.reminder_lead_hours)
            if now >= matter.due_at:
                overdue_by = now - matter.due_at
                escalated = overdue_by >= timedelta(hours=tpl.escalate_hours)
                created.append(_ensure_reminder(
                    matter, "escalated" if escalated else "overdue",
                    "escalate" if escalated else "overdue",
                    f"{matter.code} {'超期升级' if escalated else '已超期'}：{matter.title}",
                    f"处置时限已过 {overdue_by.total_seconds() / 3600:.1f} 小时，请立即处置。",
                    matter.due_at, now,
                ))
            elif now >= matter.due_at - lead:
                created.append(_ensure_reminder(
                    matter, "due_soon", "warn",
                    f"{matter.code} 临近到期：{matter.title}",
                    f"距处置到期不足 {tpl.reminder_lead_hours} 小时，请抓紧办理。",
                    matter.due_at, now,
                ))
    return [item for item in created if item is not None]


def close_reminders(matter):
    return matter.reminders.filter(status__in=("pending",)).update(status="closed")


def ack_reminder(reminder, *, actor=None, actor_name=""):
    reminder.status = "ack"
    reminder.ack_by = actor if getattr(actor, "is_authenticated", False) else None
    reminder.ack_name = _actor_label(actor, actor_name) or "值班人员"
    reminder.ack_at = timezone.now()
    reminder.save()
    return reminder


# --------------------------------------------------------------------------- #
# 数据统计
# --------------------------------------------------------------------------- #
def _avg_hours(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def matter_brief(matter):
    return {
        "id": str(matter.id),
        "code": matter.code,
        "title": matter.title,
        "location": matter.location,
        "template": matter.template.code,
        "templateName": matter.template.name,
        "templateIcon": matter.template.icon,
        "templateColor": matter.template.color,
        "category": matter.template.category,
        "status": matter.status,
        "statusName": matter.status_name,
        "priority": matter.priority,
        "priorityName": matter.get_priority_display(),
        "source": matter.source,
        "urgency": matter.urgency,
        "progress": matter.progress_percent,
        "reporter": matter.reporter_name,
        "handler": matter.handler_name,
        "isOverdue": matter.is_overdue,
        "isDemo": matter.is_demo,
        "submittedAt": timezone.localtime(matter.submitted_at).strftime("%Y-%m-%d %H:%M"),
        "dueAt": timezone.localtime(matter.due_at).strftime("%Y-%m-%d %H:%M") if matter.due_at else None,
        "closedAt": timezone.localtime(matter.closed_at).strftime("%Y-%m-%d %H:%M") if matter.closed_at else None,
        "ageHours": round(matter.age_hours, 1),
        "remainingHours": round(matter.remaining_hours, 1) if matter.remaining_hours is not None else None,
        "pendingReminders": matter.reminders.filter(status="pending").count(),
    }


def matter_detail(matter):
    data = matter_brief(matter)
    data.update({
        "detail": matter.detail,
        "payload": matter.payload or {},
        "hasPhoto": bool(matter.photo),
        "photoUrl": f"/api/matters/{matter.id}/photo/" if matter.photo else None,
        "reporterContact": matter.reporter_contact,
        "stages": matter.template.stage_list(),
        "stageNames": matter.template.stage_names(),
        "fields": matter.template.field_list(),
        "currentStageIndex": STATUS_ORDER.index(matter.status) if matter.status in STATUS_ORDER else -1,
        "sla": {
            "acceptHours": matter.template.accept_sla_hours,
            "handleHours": matter.template.handle_sla_hours,
            "totalHours": matter.template.total_sla_hours,
            "leadHours": matter.template.reminder_lead_hours,
        },
        "timeline": matter_timeline(matter),
        "reminders": [reminder_brief(item) for item in matter.reminders.all()[:20]],
    })
    return data


def matter_timeline(matter):
    return [
        {
            "kind": event.kind,
            "kindName": event.get_kind_display(),
            "fromStatus": event.from_status,
            "toStatus": event.to_status,
            "note": event.note,
            "actor": event.actor_name or "—",
            "at": timezone.localtime(event.created_at).strftime("%Y-%m-%d %H:%M"),
        }
        for event in matter.events.all()
    ]


def reminder_brief(reminder):
    return {
        "id": reminder.id,
        "matterId": str(reminder.matter_id),
        "code": reminder.matter.code,
        "title": reminder.title,
        "body": reminder.body,
        "level": reminder.level,
        "levelName": reminder.get_level_display(),
        "rule": reminder.rule,
        "ruleName": reminder.get_rule_display(),
        "status": reminder.status,
        "statusName": reminder.get_status_display(),
        "templateName": reminder.matter.template.name,
        "templateIcon": reminder.matter.template.icon,
        "templateColor": reminder.matter.template.color,
        "triggeredAt": timezone.localtime(reminder.triggered_at).strftime("%m-%d %H:%M"),
        "ackName": reminder.ack_name,
    }


def scenario_stats(now=None):
    now = now or timezone.now()
    items = []
    for template in ScenarioTemplate.objects.filter(is_active=True):
        matters = list(template.matters.all())
        total = len(matters)
        open_items = [m for m in matters if m.is_open]
        overdue = [m for m in open_items if m.is_overdue]
        done = [m for m in matters if m.status == "done"]
        on_time = [m for m in done if m.due_at and m.closed_at and m.closed_at <= m.due_at]
        items.append({
            "code": template.code,
            "name": template.name,
            "category": template.category,
            "icon": template.icon,
            "color": template.color,
            "summary": template.summary,
            "isEmergency": template.is_emergency,
            "slaHours": template.total_sla_hours,
            "total": total,
            "open": len(open_items),
            "overdue": len(overdue),
            "done": len(done),
            "rejected": sum(1 for m in matters if m.status == "rejected"),
            "submitted": sum(1 for m in matters if m.status == "submitted"),
            "processing": sum(1 for m in matters if m.status == "processing"),
            "completionRate": round(len(done) / total * 100) if total else 0,
            "onTimeRate": round(len(on_time) / len(done) * 100) if done else None,
            "avgHours": _avg_hours([m.age_hours for m in done]),
        })
    return items


def overview_stats(now=None):
    now = now or timezone.now()
    today = timezone.localdate()
    matters = list(HealthMatter.objects.select_related("template").all())
    open_items = [m for m in matters if m.is_open]
    overdue = [m for m in open_items if m.is_overdue]
    done = [m for m in matters if m.status == "done"]
    on_time = [m for m in done if m.due_at and m.closed_at and m.closed_at <= m.due_at]
    soon = [m for m in open_items if m.urgency in ("soon", "urgent")]
    payload = {
        "generatedAt": timezone.localtime(now).strftime("%Y-%m-%d %H:%M"),
        "totals": {
            "all": len(matters),
            "open": len(open_items),
            "overdue": len(overdue),
            "soon": len(soon),
            "done": len(done),
            "today": sum(1 for m in matters if timezone.localtime(m.submitted_at).date() == today),
            "todayClosed": sum(1 for m in done if m.closed_at and timezone.localtime(m.closed_at).date() == today),
            "completionRate": round(len(done) / len(matters) * 100) if matters else 0,
            "onTimeRate": round(len(on_time) / len(done) * 100) if done else None,
            "avgHours": _avg_hours([m.age_hours for m in done]),
            "templates": ScenarioTemplate.objects.filter(is_active=True).count(),
        },
        "statusDistribution": [
            {"key": key, "name": name, "value": sum(1 for m in matters if m.status == key)}
            for key, name in HealthMatter.STATUS_CHOICES
        ],
        "scenarios": scenario_stats(now),
        "trend": daily_trend(14, now),
        "reminders": reminder_summary(now),
        "topOverdue": [matter_brief(m) for m in sorted(
            overdue, key=lambda m: m.due_at)[:6]],
    }
    return payload


def daily_trend(days=14, now=None):
    now = now or timezone.now()
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    matters = HealthMatter.objects.filter(submitted_at__date__gte=start).only(
        "submitted_at", "closed_at")
    buckets = {start + timedelta(days=i): {"date": (start + timedelta(days=i)).strftime("%m-%d"),
                                           "submitted": 0, "closed": 0}
               for i in range(days)}
    for matter in matters:
        key = timezone.localtime(matter.submitted_at).date()
        if key in buckets:
            buckets[key]["submitted"] += 1
        if matter.closed_at:
            close_key = timezone.localtime(matter.closed_at).date()
            if close_key in buckets:
                buckets[close_key]["closed"] += 1
    return list(buckets.values())


def reminder_summary(now=None):
    now = now or timezone.now()
    pending = Reminder.objects.filter(status="pending").select_related("matter", "matter__template")
    return {
        "pending": pending.count(),
        "overdue": pending.filter(level="overdue").count(),
        "escalate": pending.filter(level="escalate").count(),
        "warn": pending.filter(level="warn").count(),
        "today": pending.filter(triggered_at__date=timezone.localdate(now)).count(),
        "items": [reminder_brief(item) for item in pending[:12]],
    }


def recent_events(limit=24):
    events = MatterEvent.objects.select_related("matter", "matter__template").order_by("-created_at")[:limit]
    return [
        {
            "kind": event.kind,
            "kindName": event.get_kind_display(),
            "code": event.matter.code,
            "title": event.matter.title,
            "templateName": event.matter.template.name,
            "templateColor": event.matter.template.color,
            "templateIcon": event.matter.template.icon,
            "note": event.note,
            "actor": event.actor_name or "系统",
            "at": timezone.localtime(event.created_at).strftime("%m-%d %H:%M"),
        }
        for event in events
    ]


def period_summary(days=7, now=None):
    """近 N 天的处理效能，用于驾驶舱的趋势解读。"""
    now = now or timezone.now()
    since = now - timedelta(days=days)
    created = HealthMatter.objects.filter(submitted_at__gte=since)
    closed = HealthMatter.objects.filter(closed_at__gte=since, status="done")
    by_scenario = [
        {"name": row["template__name"], "icon": row["template__icon"],
         "color": row["template__color"], "count": row["count"]}
        for row in created.values("template__name", "template__icon", "template__color")
        .annotate(count=Count("id")).order_by("-count")
    ]
    return {
        "days": days,
        "created": created.count(),
        "closed": closed.count(),
        "byScenario": by_scenario,
    }


# --------------------------------------------------------------------------- #
# 地图点位（已处理 = 绿，未处理 = 红）
# --------------------------------------------------------------------------- #
def _clamp_percent(value, default=50.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.0, min(100.0, number)), 2)


def map_point_brief(point, now=None):
    now = now or timezone.now()
    last_done = timezone.localtime(point.last_done_at) if point.last_done_at else None
    days = None
    if last_done:
        days = max(0, (timezone.localdate(now) - last_done.date()).days)
    return {
        "id": point.id,
        "name": point.name,
        "category": point.category,
        "categoryName": point.get_category_display(),
        "mapX": round(point.map_x, 2),
        "mapY": round(point.map_y, 2),
        "status": point.status,
        "statusName": point.status_name,
        "isDone": point.status == "done",
        "isCustom": point.is_custom,
        "note": point.note,
        "lastDoneAt": last_done.strftime("%Y-%m-%d %H:%M") if last_done else None,
        "lastDoneDays": days,
        "lastActionBy": point.last_action_by,
        "createdBy": point.created_by_name,
        "createdAt": timezone.localtime(point.created_at).strftime("%Y-%m-%d %H:%M"),
    }


def map_point_stats(points=None, now=None):
    points = list(points if points is not None else MapPoint.objects.all())
    done = sum(1 for item in points if item.status == "done")
    total = len(points)
    return {
        "total": total,
        "done": done,
        "pending": total - done,
        "custom": sum(1 for item in points if item.is_custom),
        "rate": round(done / total * 100) if total else 0,
    }


def map_point_queryset():
    """未处理点位排在前面，方便督办；同类按最近更新排序。"""
    from django.db.models import Case, IntegerField, Value, When
    return MapPoint.objects.annotate(
        _pending_first=Case(When(status="pending", then=Value(0)), default=Value(1), output_field=IntegerField())
    ).order_by("_pending_first", "-updated_at", "id")


def create_map_point(*, name, category="other", map_x=50, map_y=50, note="",
                     operator_name="", source_ref="", is_custom=True, is_demo=False,
                     status="pending", last_done_at=None):
    """新增点位：坐标按底图百分比保存，默认状态为「未处理」。"""
    if status not in dict(MapPoint.STATUS_CHOICES):
        status = "pending"
    point = MapPoint.objects.create(
        name=name.strip()[:60],
        category=category if category in dict(MapPoint.CATEGORY_CHOICES) else "other",
        map_x=_clamp_percent(map_x),
        map_y=_clamp_percent(map_y),
        status=status,
        note=(note or "").strip()[:180],
        is_custom=is_custom,
        source_ref=(source_ref or "")[:40],
        last_done_at=last_done_at,
        created_by_name=(operator_name or "").strip()[:60],
        last_action_by=(operator_name or "").strip()[:60],
        is_demo=is_demo,
    )
    return point


def set_map_point_status(point, status, *, operator_name="", note=""):
    """标记点位已处理 / 未处理，并保留最近处理时间，形成可追溯的处理台账。"""
    if status not in dict(MapPoint.STATUS_CHOICES):
        raise ValueError(f"未知点位状态：{status}")
    now = timezone.now()
    point.status = status
    if status == "done":
        point.last_done_at = now
    if operator_name:
        point.last_action_by = operator_name.strip()[:60]
    if note:
        point.note = note.strip()[:180]
    point.save()
    return point


def update_map_point_position(point, map_x, map_y):
    point.map_x = _clamp_percent(map_x, point.map_x)
    point.map_y = _clamp_percent(map_y, point.map_y)
    point.save(update_fields=["map_x", "map_y", "updated_at"])
    return point

