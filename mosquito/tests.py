import json
import tempfile
import uuid
from io import BytesIO

from PIL import Image
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from .admin import HazardReportAdminForm
from .models import HazardReport, InspectionLog, InspectionPoint
from .models import CampusMap, CampusArea, AreaTreatment, DormRoom


class ManagementPortalTests(TestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_superuser('portal-manager', password='Test-password-827!')

    def test_student_registration_cannot_manage(self):
        response = self.client.post('/account/?mode=register', {'role': 'student', 'identifier': '20260001',
            'name': '测试学生', 'password': 'Test-password-827!', 'confirm': 'Test-password-827!'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.get(username='student:20260001').is_staff)
        self.assertEqual(self.client.get('/manage/').status_code, 403)

    def test_teacher_does_not_gain_staff(self):
        response = self.client.post('/account/?mode=register', {'role': 'teacher', 'identifier': '13800000000',
            'name': '测试教师', 'password': 'Test-password-827!', 'confirm': 'Test-password-827!'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get('/manage/').status_code, 403)

    def test_rooms_and_map_scoping(self):
        self.client.force_login(self.manager)
        for building in ['8栋', '9栋', '10栋']:
            self.assertEqual(self.client.post('/manage/?action=rooms', {'building': building, 'numbers': '101,102', 'is_demo': 'on'}).status_code, 302)
        self.assertEqual(DormRoom.objects.count(), 6)
        custom = CampusMap.objects.create(name='管理者自定义地图')
        CampusArea.objects.create(name='自定义点', map_x=20, map_y=40, campus_map=custom)
        self.assertEqual(len(self.client.get('/api/areas/').json()['areas']), 0)
        self.assertEqual(len(self.client.get(f'/api/areas/?map={custom.pk}').json()['areas']), 1)

    def test_point_and_treatment_are_saved(self):
        self.client.force_login(self.manager)
        response = self.client.post('/manage/?action=area', {'name': '人工选定区域', 'category': 'dining',
            'map_x': '12', 'map_y': '34', 'interval_days': '10', 'is_active': 'on', 'is_demo': 'on'})
        self.assertEqual(response.status_code, 302)
        area = CampusArea.objects.get(name='人工选定区域')
        self.assertEqual(area.interval_days, 10)
        response = self.client.post('/manage/?action=treatment', {'area': area.pk, 'method': 'cleanup',
            'treated_at': '2026-10-11T12:00', 'operator': '测试班组', 'note': '处理登记测试', 'is_demo': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AreaTreatment.objects.get().recorded_by, self.manager)
        self.assertEqual(len(self.client.get('/api/areas/').json()['areas'][0]['history']), 1)

    def test_staff_without_model_permission_is_denied(self):
        user = get_user_model().objects.create_user('limited', password='Test-password-827!', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.post('/manage/?action=rooms', {'building': '8栋', 'numbers': '101'}).status_code, 403)

    def test_all_management_forms_render(self):
        self.client.force_login(self.manager)
        for action in ['map', 'area', 'treatment', 'rooms', 'campaign']:
            self.assertEqual(self.client.get(f'/manage/?action={action}').status_code, 200)
        self.assertEqual(self.client.get('/account/').status_code, 200)

    def test_anonymous_dorm_submission_requires_login(self):
        self.assertEqual(self.client.post('/api/dorm-records/', {}).status_code, 401)


class ReportApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.payload = {
            "location": "教学楼东侧花盆（演示）",
            "type": "花盆托盘积水",
            "detail": "虚构线索，用于验证上报流程",
        }

    def test_submit_then_read_receipt_with_csrf(self):
        page = self.client.get("/report.html")
        self.assertEqual(page.status_code, 200)
        self.assertIn("csrftoken", page.cookies)
        token = page.cookies["csrftoken"].value
        response = self.client.post(
            "/api/reports/", data=json.dumps(self.payload), content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201)
        report_id = response.json()["id"]
        self.assertEqual(HazardReport.objects.count(), 1)
        self.assertTrue(HazardReport.objects.get(id=report_id).is_demo)
        detail = self.client.get(f"/api/reports/{report_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["status"], "pending")
        self.assertEqual(detail.json()["location"], self.payload["location"])

    def test_public_submit_requires_csrf(self):
        response = self.client.post(
            "/api/reports/", data=json.dumps(self.payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(HazardReport.objects.count(), 0)

    def test_photo_upload_is_saved_and_only_viewable_by_admin(self):
        image_data = BytesIO()
        Image.new("RGB", (8, 8), "green").save(image_data, format="PNG")
        photo_bytes = image_data.getvalue()
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            token = self.client.get("/report.html").cookies["csrftoken"].value
            response = self.client.post(
                "/api/reports/",
                data={**self.payload, "photo": SimpleUploadedFile("evidence.png", photo_bytes, content_type="image/png")},
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertTrue(response.json()["hasPhoto"])
            report = HazardReport.objects.get(id=response.json()["id"])
            self.assertTrue(report.photo.storage.exists(report.photo.name))
            self.assertTrue(report.photo.name.endswith(".png"))
            photo_url = reverse("report-photo", args=[report.id])
            self.assertEqual(self.client.get(photo_url).status_code, 302)

            staff = get_user_model().objects.create_user("staff_only", password="test-only-password", is_staff=True)
            self.client.force_login(staff)
            self.assertEqual(self.client.get(photo_url).status_code, 403)
            administrator = get_user_model().objects.create_superuser("photo_admin", "admin@example.invalid", "test-only-password")
            self.client.force_login(administrator)
            image_response = self.client.get(photo_url)
            self.assertEqual(image_response.status_code, 200)
            self.assertEqual(image_response["Content-Type"], "image/png")
            self.assertEqual(b"".join(image_response.streaming_content), photo_bytes)
            change = self.client.get(reverse("admin:mosquito_hazardreport_change", args=[report.id]))
            self.assertContains(change, "打开原图")
            self.assertContains(change, photo_url)

    def test_invalid_photo_is_rejected_without_saving_report(self):
        token = self.client.get("/report.html").cookies["csrftoken"].value
        response = self.client.post(
            "/api/reports/",
            data={**self.payload, "photo": SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")},
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(HazardReport.objects.count(), 0)

    def test_invalid_data_rejected(self):
        token = self.client.get("/report/").cookies["csrftoken"].value
        self.payload["type"] = "其他任意类别"
        response = self.client.post(
            "/api/reports/", data=json.dumps(self.payload), content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(HazardReport.objects.count(), 0)

    def test_no_public_list_or_guessable_missing_receipt(self):
        self.assertEqual(self.client.get("/api/reports/").status_code, 405)
        self.assertEqual(self.client.get(f"/api/reports/{uuid.uuid4()}/").status_code, 404)


class AdminTests(TestCase):
    def test_models_registered_and_admin_requires_login(self):
        for model in (HazardReport, InspectionPoint, InspectionLog):
            self.assertIn(model, admin.site._registry)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        user = get_user_model().objects.create_superuser("test_admin", "test@example.invalid", "test-only-password")
        self.client.force_login(user)
        dashboard = self.client.get("/admin/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "校园公共卫生")
        self.assertContains(dashboard, "/admin/mosquito/hazardreport/")

    def test_resolved_status_requires_processing_note(self):
        report = HazardReport.objects.create(location="测试点位", kind="桶盆积水")
        fields = {"location": report.location, "kind": report.kind, "detail": "", "status": "resolved", "is_demo": True}
        incomplete = HazardReportAdminForm(data={**fields, "processing_note": ""}, instance=report)
        self.assertFalse(incomplete.is_valid())
        self.assertIn("processing_note", incomplete.errors)
        complete = HazardReportAdminForm(data={**fields, "processing_note": "已清理积水并复查"}, instance=report)
        self.assertTrue(complete.is_valid(), complete.errors)
        complete.save()
        receipt = self.client.get(f"/api/reports/{report.id}/").json()
        self.assertEqual(receipt["status"], "resolved")
        self.assertEqual(receipt["processingNote"], "已清理积水并复查")
