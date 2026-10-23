import json
import tempfile
import uuid
from io import BytesIO
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from mosquito.models import AccountProfile, DormRoom
from .hygiene import RULES
from .hygiene_models import DormBinding, HygieneInspector, DormInspection, HygieneEvidence


class HygieneTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        setting = override_settings(MEDIA_ROOT=self.tmp.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.inspector = self.make_student('student:inspector')
        self.resident = self.make_student('student:resident')
        self.stranger = self.make_student('student:stranger')
        HygieneInspector.objects.create(user=self.inspector)
        self.room = DormRoom.objects.create(building='演示楼', room_number='101')
        self.other = DormRoom.objects.create(building='演示楼', room_number='102')
        self.client.force_login(self.inspector)

    def make_student(self, name):
        user = get_user_model().objects.create_user(username=name)
        AccountProfile.objects.create(user=user, identifier=name, role='student')
        return user

    def post(self, path, data):
        return self.client.post('/api/v1/hygiene/'+path, json.dumps(data), content_type='application/json')

    def photo(self, key='floor'):
        stream = BytesIO()
        Image.new('RGB', (10, 10)).save(stream, format='PNG')
        r = self.client.post('/api/v1/hygiene/evidence/', {'itemKey': key, 'photo': SimpleUploadedFile('demo.png', stream.getvalue(), content_type='image/png')})
        self.assertEqual(r.status_code, 201)
        return r.json()['id']

    def payload(self, deduct=0):
        items = [{'key': key, 'deduction': deduct if index == 0 else 0, 'reason': '演示扣分依据' if index == 0 else ''} for index, (key, label) in enumerate(RULES)]
        if deduct:
            items[0]['evidenceId'] = self.photo()
        return {'submissionKey': uuid.uuid4().hex, 'roomId': self.room.pk, 'date': str(timezone.localdate()), 'items': items, 'score': 0, 'passed': False}

    def create_record(self, deduct=0):
        data = self.payload(deduct)
        r = self.post('records/', data)
        self.assertEqual(r.status_code, 201, r.content)
        return DormInspection.objects.get(pk=r.json()['id']), data

    def test_server_calculates_score_and_80_passes(self):
        record, data = self.create_record(20)
        self.assertEqual(record.score, 80)
        self.assertTrue(record.passed)
        self.assertEqual(record.evidence.count(), 1)

    def test_below_80_fails(self):
        data = self.payload(20)
        data['items'][1].update(deduction=1, reason='床铺问题', evidenceId=self.photo('bed'))
        self.assertEqual(self.post('records/', data).status_code, 201)
        self.assertFalse(DormInspection.objects.get().passed)
        self.assertEqual(DormInspection.objects.get().score, 79)

    def test_ordinary_student_cannot_self_authorize(self):
        self.client.force_login(self.resident)
        self.assertEqual(self.post('records/', {'canInspect': True}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/hygiene/evidence/', {}).status_code, 403)

    def test_revoked_inspector_cannot_write(self):
        HygieneInspector.objects.update(active=False)
        self.assertEqual(self.post('records/', {}).status_code, 403)

    def test_binding_ignores_client_approval_and_change_revokes_access(self):
        self.client.force_login(self.resident)
        self.assertEqual(self.post('binding/', {'roomId': self.room.pk, 'approved': True}).status_code, 200)
        b = DormBinding.objects.get(user=self.resident)
        self.assertFalse(b.approved)
        b.approved = True
        b.save()
        self.post('binding/', {'roomId': self.other.pk})
        b.refresh_from_db()
        self.assertFalse(b.approved)

    def test_deduction_requires_reason_and_photo(self):
        data = self.payload()
        data['items'][0].update(deduction=2, reason='')
        self.assertEqual(self.post('records/', data).status_code, 400)
        data['items'][0]['reason'] = '未清扫'
        self.assertEqual(self.post('records/', data).status_code, 400)
        self.assertEqual(DormInspection.objects.count(), 0)

    def test_invalid_and_missing_items_rejected(self):
        for value in [-1, 21, 1.2, True, '2']:
            data = self.payload()
            data['items'][0]['deduction'] = value
            self.assertEqual(self.post('records/', data).status_code, 400)
        data = self.payload()
        data['items'].pop()
        self.assertEqual(self.post('records/', data).status_code, 400)

    def test_duplicate_submission_is_idempotent(self):
        record, data = self.create_record(1)
        r = self.post('records/', data)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['id'], str(record.id))
        self.assertEqual(DormInspection.objects.count(), 1)

    def test_cross_student_and_unapproved_binding_cannot_read_photos(self):
        record, data = self.create_record(1)
        photo = data['items'][0]['evidenceId']
        self.client.force_login(self.resident)
        DormBinding.objects.create(user=self.resident, room=self.room)
        self.assertEqual(self.client.get(f'/api/v1/hygiene/records/{record.pk}/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/hygiene/photos/{photo}/').status_code, 403)
        DormBinding.objects.filter(user=self.resident).update(approved=True)
        self.assertEqual(self.client.get(f'/api/v1/hygiene/records/{record.pk}/').status_code, 200)
        r = self.client.get(f'/api/v1/hygiene/photos/{photo}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Cache-Control'], 'private, no-store')
        r.close()
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get('/api/v1/hygiene/').json()['records'], [])
        self.assertEqual(self.client.get(f'/api/v1/hygiene/photos/{photo}/').status_code, 403)

    def test_cannot_reuse_other_owners_or_other_items_evidence(self):
        data = self.payload(1)
        p = HygieneEvidence.objects.get()
        p.owner = self.resident
        p.save()
        self.assertEqual(self.post('records/', data).status_code, 400)
        p.owner = self.inspector
        p.item_key = 'bed'
        p.save()
        self.assertEqual(self.post('records/', data).status_code, 400)

    def test_teacher_is_not_student_inspector(self):
        AccountProfile.objects.filter(user=self.inspector).update(role='teacher')
        self.assertEqual(self.post('records/', {}).status_code, 403)

    def test_anonymous_and_unattached_photo_denied(self):
        photo = self.photo()
        self.assertEqual(self.client.get(f'/api/v1/hygiene/photos/{photo}/').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get('/api/v1/hygiene/').status_code, 403)

    def test_existing_record_is_immutable_and_history_accumulates(self):
        record, _ = self.create_record()
        self.create_record()
        self.assertEqual(DormInspection.objects.filter(room=self.room).count(), 2)
        self.assertEqual(self.client.post(f'/api/v1/hygiene/records/{record.pk}/', {}).status_code, 405)
