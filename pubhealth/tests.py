"""公共卫生事项引擎测试：报备、进度跟踪、自动提醒、统计四个环节。"""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from pubhealth.models import HealthMatter, MapPoint, MatterEvent, Reminder, ScenarioTemplate
from pubhealth.scenarios import SCENARIOS
from pubhealth.services import (create_map_point, create_matter, generate_reminders, overview_stats,
                               transition)


class ScenarioTemplateTests(TestCase):
    def test_home_and_separate_login_entries(self):
        self.assertContains(self.client.get('/'), '健康知识')
        manager = self.client.get('/account/?entry=manager').content.decode()
        user = self.client.get('/account/?entry=user').content.decode()
        self.assertIn('value="manager"', manager)
        self.assertNotIn('value="student"', manager)
        self.assertIn('value="student"', user)
        self.assertIn('value="teacher"', user)
        self.assertNotIn('value="manager"', user)

    def test_map_points_are_scoped_to_uploaded_map(self):
        from mosquito.models import CampusMap
        admin = get_user_model().objects.create_superuser('scope-manager', password='Test-password-827!')
        self.client.force_login(admin)
        campus_map = CampusMap.objects.create(name='自定义测试地图', image='campus-maps/test.png')
        response = self.client.post('/api/v1/map/points/create/', data=json.dumps({
            'name': '人工添加测试点', 'map': str(campus_map.pk), 'x': 25, 'y': 40}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        point = MapPoint.objects.get(pk=response.json()['point']['id'])
        self.assertEqual(point.campus_map, campus_map)
        self.assertEqual(point.status, 'pending')
        self.assertEqual(self.client.get('/api/v1/map/points/').json()['points'], [])
        self.assertEqual(len(self.client.get(f'/api/v1/map/points/?map={campus_map.pk}').json()['points']), 1)

    def test_seed_creates_six_scenarios(self):
        for item in SCENARIOS:
            ScenarioTemplate.objects.create(**{**item, "is_demo": True})
        self.assertEqual(ScenarioTemplate.objects.count(), 6)
        self.assertEqual(
            set(ScenarioTemplate.objects.values_list("code", flat=True)),
            {"vector-control", "infectious-report", "hygiene-inspection",
             "area-disinfection", "health-education", "emergency-report"},
        )
        vector = ScenarioTemplate.objects.get(code="vector-control")
        self.assertTrue(vector.field_list())
        self.assertEqual(len(vector.stage_list()), 5)
        self.assertEqual(vector.total_sla_hours, vector.accept_sla_hours + vector.handle_sla_hours)


class MatterWorkflowTests(TestCase):
    def setUp(self):
        self.template = ScenarioTemplate.objects.create(**{**SCENARIOS[0], "is_demo": True})
        self.now = timezone.now()

    def test_create_generates_code_and_first_event(self):
        matter = create_matter(self.template, title="测试积水", location="9栋后方")
        self.assertRegex(matter.code, r"^WZ-\d{8}-\d{4}$")
        self.assertEqual(matter.status, "submitted")
        self.assertEqual(matter.events.count(), 1)
        self.assertEqual(matter.events.first().kind, "created")
        expected = self.template.accept_sla_hours + self.template.handle_sla_hours
        self.assertAlmostEqual((matter.due_at - matter.submitted_at).total_seconds() / 3600, expected, places=1)

    def test_transition_writes_traceable_events(self):
        matter = create_matter(self.template, title="测试积水", location="9栋后方")
        transition(matter, "accepted", actor_name="管理员", note="已受理")
        transition(matter, "processing", actor_name="消杀一班")
        matter.refresh_from_db()
        self.assertEqual(matter.status, "processing")
        self.assertIsNotNone(matter.accepted_at)
        self.assertEqual(matter.events.count(), 3)
        kinds = list(matter.events.values_list("kind", flat=True))
        self.assertEqual(kinds, ["created", "status", "status"])
        self.assertEqual(matter.progress_percent, 50)

    def test_illegal_status_rejected(self):
        matter = create_matter(self.template, title="测试", location="位置")
        with self.assertRaises(ValueError):
            transition(matter, "unknown-status")

    def test_done_closes_reminders(self):
        matter = create_matter(self.template, title="测试", location="位置", submitted_at=self.now - timedelta(days=4))
        generate_reminders(queryset=HealthMatter.objects.filter(pk=matter.pk).select_related("template"))
        self.assertGreater(matter.reminders.count(), 0)
        transition(matter, "done", actor_name="复核人")
        self.assertFalse(matter.reminders.filter(status="pending").exists())


class ReminderEngineTests(TestCase):
    def setUp(self):
        self.vector = ScenarioTemplate.objects.create(**{**SCENARIOS[0], "is_demo": True})
        self.emergency = ScenarioTemplate.objects.create(**{**SCENARIOS[-1], "is_demo": True})

    def test_overdue_and_due_soon_rules(self):
        overdue = create_matter(self.vector, title="超期事项", location="A",
                                submitted_at=timezone.now() - timedelta(days=10))
        soon = create_matter(self.vector, title="临期事项", location="B",
                             submitted_at=timezone.now() - timedelta(hours=self.vector.total_sla_hours - 2))
        generate_reminders()
        # 超期已超过升级阈值，应升级为 escalated；未超过阈值时为 overdue。
        self.assertTrue(overdue.reminders.filter(rule__in=("overdue", "escalated")).exists())
        self.assertTrue(soon.reminders.filter(rule="due_soon").exists())

    def test_overdue_within_escalation_window(self):
        stuck = create_matter(self.vector, title="刚超期事项", location="D",
                              submitted_at=timezone.now() - timedelta(
                                  hours=self.vector.total_sla_hours + 1))
        generate_reminders()
        self.assertTrue(stuck.reminders.filter(rule="overdue").exists())

    def test_accept_sla_rule_and_escalation(self):
        stale = create_matter(self.emergency, title="未受理应急", location="C",
                              submitted_at=timezone.now() - timedelta(hours=self.emergency.accept_sla_hours + 5))
        generate_reminders()
        self.assertTrue(stale.reminders.filter(rule="accept_sla").exists())

    def test_reminder_generation_is_idempotent(self):
        create_matter(self.vector, title="超期事项", location="A",
                      submitted_at=timezone.now() - timedelta(days=10))
        first = generate_reminders()
        second = generate_reminders()
        self.assertGreater(len(first), 0)
        self.assertEqual(len(second), 0)
        self.assertEqual(Reminder.objects.count(), len(first))

    def test_overview_stats_shape(self):
        create_matter(self.vector, title="统计事项", location="A",
                      submitted_at=timezone.now() - timedelta(days=10))
        generate_reminders()
        stats = overview_stats()
        self.assertEqual(stats["totals"]["all"], 1)
        self.assertEqual(stats["totals"]["overdue"], 1)
        self.assertGreaterEqual(stats["reminders"]["overdue"] + stats["reminders"]["escalate"], 1)
        self.assertEqual(len(stats["statusDistribution"]), 6)
        self.assertEqual(len(stats["scenarios"]), 2)


class PublicApiTests(TestCase):
    def setUp(self):
        self.template = ScenarioTemplate.objects.create(**{**SCENARIOS[0], "is_demo": True})

    def test_public_pages_render_and_cockpit_asks_login(self):
        # 报备与进度跟踪对公众开放
        self.assertEqual(self.client.get("/report/").status_code, 200)
        # 驾驶舱改为管理端：访客先去登录，登录后回到驾驶舱
        self.assertContains(self.client.get('/'), '健康知识')
        redirect = self.client.get("/cockpit/")
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect["Location"], "/account/?next=/cockpit/")
        # 线上报备与进度查询已合并：/track/ 统一跳转到报备页的进度区块
        redirect = self.client.get("/track/")
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect["Location"], "/report/#track")
        html = self.client.get("/report/").content.decode("utf-8")
        self.assertIn('id="track"', html)
        self.assertIn('id="report"', html)
        self.assertNotIn('class="tab ', html)

    def test_cockpit_open_for_manager_only(self):
        manager = get_user_model().objects.create_superuser("ph-cockpit-manager", password="Test-password-827!")
        self.client.force_login(manager)
        self.assertEqual(self.client.get("/cockpit/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/overview/").status_code, 200)

    def test_student_cannot_open_cockpit(self):
        user = get_user_model().objects.create_user("student:2025001", password="Test-password-827!")
        self.client.force_login(user)
        redirect = self.client.get("/cockpit/")
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect["Location"], "/account/?next=/cockpit/")
        denied = self.client.get("/api/v1/overview/")
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(denied.json()["loginRequired"])

    def test_management_apis_require_login(self):
        for url in ("/api/v1/overview/", "/api/v1/matters/list/", "/api/v1/reminders/",
                    "/api/v1/timeline/", "/api/v1/map/points/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)
            self.assertTrue(response.json()["loginRequired"], url)
        created = self.client.post("/api/v1/map/points/create/",
                                   data=json.dumps({"name": "访客点位", "x": 10, "y": 10}),
                                   content_type="application/json")
        self.assertEqual(created.status_code, 403)
        self.assertEqual(MapPoint.objects.count(), 0)

    def test_account_login_honours_next_and_role(self):
        get_user_model().objects.create_superuser("ph-login-manager", password="Test-password-827!")
        html = self.client.get("/account/?next=/").content.decode("utf-8")
        self.assertIn('name="next" value="/"', html)
        redirect = self.client.post("/account/", {"role": "manager", "identifier": "ph-login-manager",
                                                 "password": "Test-password-827!", "next": "/report/#track"})
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect["Location"], "/report/#track")
        self.client.logout()
        # 学生登录不会被打回驾驶舱，而是进报备页
        get_user_model().objects.create_user("student:2025002", password="Test-password-827!")
        redirect = self.client.post("/account/", {"role": "student", "identifier": "2025002",
                                                 "password": "Test-password-827!"})
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect["Location"], "/report/")

    def test_login_next_rejects_external_url(self):
        from pubhealth.views import _safe_next
        self.assertEqual(_safe_next("https://evil.example.com", "/report/"), "/report/")
        self.assertEqual(_safe_next("//evil.example.com", "/report/"), "/report/")
        self.assertEqual(_safe_next("/api/v1/overview/", "/report/"), "/api/v1/overview/")

    def test_student_next_to_cockpit_falls_back_to_report(self):
        get_user_model().objects.create_user("student:2025003", password="Test-password-827!")
        redirect = self.client.post("/account/", {"role": "student", "identifier": "2025003",
                                                 "password": "Test-password-827!", "next": "/"})
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect["Location"], "/report/")

    def test_scenarios_api_exposes_fields(self):
        response = self.client.get("/api/v1/scenarios/")
        self.assertEqual(response.status_code, 200)
        item = response.json()["scenarios"][0]
        self.assertIn("fields", item)
        self.assertIn("stages", item)

    def test_report_and_track_flow(self):
        response = self.client.post("/api/v1/matters/", {
            "template": self.template.code, "title": "线上报备测试", "location": "测试地点",
            "field_hazard": "排水处积水", "field_scale": "10",
        })
        self.assertEqual(response.status_code, 201, response.content)
        code = response.json()["matter"]["code"]
        track = self.client.get("/api/v1/track/", {"code": code})
        self.assertEqual(track.status_code, 200)
        self.assertEqual(track.json()["title"], "线上报备测试")

    def test_required_field_validation(self):
        response = self.client.post("/api/v1/matters/", {
            "template": self.template.code, "title": "缺字段", "location": "地点",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("隐患类型", response.json()["message"])

    def test_advance_requires_manager(self):
        matter = create_matter(self.template, title="权限测试", location="地点")
        response = self.client.post(f"/api/v1/matters/{matter.id}/advance/",
                                    data=json.dumps({"action": "accepted"}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_manager_can_advance_and_ack_reminder(self):
        manager = get_user_model().objects.create_superuser("ph-manager", password="Test-password-827!")
        self.client.force_login(manager)
        matter = create_matter(self.template, title="推进测试", location="地点",
                               submitted_at=timezone.now() - timedelta(days=10))
        generate_reminders()
        response = self.client.post(f"/api/v1/matters/{matter.id}/advance/",
                                    data=json.dumps({"action": "accepted", "note": "已受理"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        matter.refresh_from_db()
        self.assertEqual(matter.status, "accepted")
        reminder = Reminder.objects.filter(matter=matter).first()
        ack = self.client.post(f"/api/v1/reminders/{reminder.id}/ack/")
        self.assertEqual(ack.status_code, 200)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, "ack")
        self.assertTrue(matter.events.filter(kind="reminder").exists())


class MapPointTests(TestCase):
    """地图点位：自定义点位 + 已处理（绿）/ 未处理（红）标记（驾驶舱内，需管理人员登录）。"""

    def setUp(self):
        self.client = Client(SERVER_NAME="127.0.0.1")
        self.manager = get_user_model().objects.create_superuser("ph-map-manager", password="Test-password-827!")
        self.client.force_login(self.manager)

    def _create(self, **overrides):
        payload = {"name": "南门快递点旁废弃水桶", "category": "water", "x": 23.5, "y": 71.2,
                   "note": "学生报备的积水点", "operator": "生活部小王"}
        payload.update(overrides)
        return self.client.post("/api/v1/map/points/create/",
                                data=json.dumps(payload), content_type="application/json")

    def test_create_custom_point_defaults_to_pending(self):
        response = self._create()
        self.assertEqual(response.status_code, 201, response.content)
        point = MapPoint.objects.get()
        self.assertEqual(point.status, "pending")
        self.assertTrue(point.is_custom)
        self.assertAlmostEqual(point.map_x, 23.5, places=1)
        self.assertEqual(response.json()["point"]["statusName"], "未处理")
        self.assertEqual(response.json()["stats"]["pending"], 1)

    def test_position_is_clamped_to_percentage(self):
        response = self._create(x=180, y=-40)
        self.assertEqual(response.status_code, 201)
        point = MapPoint.objects.get()
        self.assertEqual(point.map_x, 100.0)
        self.assertEqual(point.map_y, 0.0)

    def test_name_required(self):
        response = self._create(name="  ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MapPoint.objects.count(), 0)

    def test_mark_done_sets_green_and_records_time(self):
        point = create_map_point(name="图书馆北侧绿化带", map_x=61, map_y=33)
        response = self.client.post(f"/api/v1/map/points/{point.id}/status/",
                                    data=json.dumps({"status": "done", "operator": "消杀一班"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        point.refresh_from_db()
        self.assertEqual(point.status, "done")
        self.assertIsNotNone(point.last_done_at)
        self.assertEqual(point.last_action_by, "消杀一班")
        self.assertEqual(response.json()["stats"]["done"], 1)

    def test_invalid_status_rejected(self):
        point = create_map_point(name="点位A")
        response = self.client.post(f"/api/v1/map/points/{point.id}/status/",
                                    data=json.dumps({"status": "half"}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_delete_requires_manager(self):
        point = create_map_point(name="待删除点位")
        anonymous = Client(SERVER_NAME="127.0.0.1")
        denied = anonymous.post(f"/api/v1/map/points/{point.id}/delete/")
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(MapPoint.objects.filter(pk=point.pk).exists())

        allowed = self.client.post(f"/api/v1/map/points/{point.id}/delete/")
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(MapPoint.objects.filter(pk=point.pk).exists())

    def test_list_exposes_stats_categories_and_pending_first(self):
        create_map_point(name="已处理点位", status="done", last_done_at=timezone.now())
        create_map_point(name="未处理点位", status="pending")
        response = self.client.get("/api/v1/map/points/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["stats"]["total"], 2)
        self.assertEqual(data["stats"]["rate"], 50)
        self.assertEqual(data["points"][0]["status"], "pending")
        self.assertTrue(any(item["key"] == "water" for item in data["categories"]))
