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
        token = self.client.get("/").cookies["csrftoken"].value
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
        self.assertContains(dashboard, "校园防蚊")
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
