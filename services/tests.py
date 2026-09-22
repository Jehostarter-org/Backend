"""End-to-end tests for the admin provider approval portal (drivers & chaperones)."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from services.models import ServiceProviderProfile

User = get_user_model()


def _extract_list(data):
    """Handle both paginated and non-paginated list responses."""
    if isinstance(data, list):
        return data
    return data.get('results', [])


class AdminProviderApprovalFlowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin1', password='pass', is_staff=True,
        )
        self.regular = User.objects.create_user(
            username='member1', password='pass',
        )

    def _driver(self, username='driver1', **kwargs):
        user = User.objects.create_user(username=username, password='pass')
        return ServiceProviderProfile.objects.create(
            user=user,
            service_type='airport_pickup',
            country_code='NG',
            city='Lagos',
            is_active=False,
            approval_status='pending',
            **kwargs,
        )

    def _chaperone(self, username='chaperone1', **kwargs):
        user = User.objects.create_user(username=username, password='pass')
        return ServiceProviderProfile.objects.create(
            user=user,
            service_type='chaperone',
            country_code='NG',
            city='Lagos',
            is_active=False,
            approval_status='pending',
            **kwargs,
        )

    # ── Access control ──────────────────────────────────────────────────────
    def test_non_admin_cannot_process_approval(self):
        profile = self._driver()
        self.client.force_authenticate(user=self.regular)
        url = reverse('admin_process_provider_approval', args=[profile.id])
        response = self.client.post(url, {'action': 'approve'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, 'pending')

    def test_anonymous_cannot_list_pending(self):
        url = reverse('admin_providers_pending')
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    # ── Approve a driver ────────────────────────────────────────────────────
    def test_admin_approves_driver(self):
        profile = self._driver()
        self.client.force_authenticate(user=self.admin)

        url = reverse('admin_process_provider_approval', args=[profile.id])
        response = self.client.post(
            url, {'action': 'approve', 'notes': 'Welcome aboard!'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'approved')

        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, 'approved')
        self.assertTrue(profile.is_active)
        self.assertEqual(profile.reviewed_by, self.admin)
        self.assertIsNotNone(profile.reviewed_at)
        self.assertEqual(profile.rejection_reason, '')

        # Approved driver no longer appears in pending list
        pending_resp = self.client.get(reverse('admin_providers_pending')).data
        pending_ids = [str(p['id']) for p in _extract_list(pending_resp)]
        self.assertNotIn(str(profile.id), pending_ids)

        # …but does appear in the all-approvals list filtered by status
        approvals_resp = self.client.get(
            reverse('admin_providers_all'), {'status': 'approved', 'service_type': 'airport_pickup'},
        ).data
        approvals = _extract_list(approvals_resp)
        self.assertEqual([str(p['id']) for p in approvals], [str(profile.id)])

    # ── Reject a chaperone ──────────────────────────────────────────────────
    def test_admin_rejects_chaperone_with_reason(self):
        profile = self._chaperone()
        self.client.force_authenticate(user=self.admin)

        url = reverse('admin_process_provider_approval', args=[profile.id])
        response = self.client.post(
            url, {'action': 'reject', 'notes': 'Missing SIM reference'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'rejected')
        self.assertEqual(response.data['reason'], 'Missing SIM reference')

        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, 'rejected')
        self.assertFalse(profile.is_active)
        self.assertEqual(profile.reviewed_by, self.admin)
        self.assertIsNotNone(profile.reviewed_at)
        self.assertEqual(profile.rejection_reason, 'Missing SIM reference')

        # Shows up in filtered list
        approvals_resp = self.client.get(
            reverse('admin_providers_all'), {'status': 'rejected', 'service_type': 'chaperone'},
        ).data
        approvals = _extract_list(approvals_resp)
        self.assertEqual([str(p['id']) for p in approvals], [str(profile.id)])

    # ── Validation ──────────────────────────────────────────────────────────
    def test_reject_requires_reason(self):
        profile = self._chaperone()
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_process_provider_approval', args=[profile.id])
        response = self.client.post(url, {'action': 'reject'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, 'pending')

    def test_invalid_action_returns_400(self):
        profile = self._driver()
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_process_provider_approval', args=[profile.id])
        response = self.client.post(url, {'action': 'nonsense'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, 'pending')

    # ── Stats ───────────────────────────────────────────────────────────────
    def test_stats_reflect_approval_decisions(self):
        d1, d2 = self._driver(), self._driver('driver2')
        c1 = self._chaperone()
        self.client.force_authenticate(user=self.admin)

        self.client.post(reverse('admin_process_provider_approval', args=[d1.id]), {'action': 'approve'}, format='json')
        self.client.post(reverse('admin_process_provider_approval', args=[c1.id]), {'action': 'reject', 'notes': 'no docs'}, format='json')

        stats = self.client.get(reverse('admin_provider_stats')).data
        self.assertEqual(stats['providers']['total'], 3)
        self.assertEqual(stats['providers']['approved'], 1)
        self.assertEqual(stats['providers']['rejected'], 1)
        self.assertEqual(stats['providers']['pending_approval'], 1)
        self.assertEqual(stats['by_service_type']['pending_drivers'], 1)
        self.assertEqual(stats['by_service_type']['pending_chaperones'], 0)
        self.assertEqual(stats['by_service_type']['drivers'], 2)
        self.assertEqual(stats['by_service_type']['chaperones'], 1)

    # ── Approval detail includes eligibility & documents ────────────────────
    def test_approval_detail_includes_eligibility_and_documents(self):
        profile = self._driver(
            first_name='Test', last_name='Driver',
            license_number='ABC123',
            license_expiration_date='2030-12-31',
            vehicle_model='Toyota', vehicle_year='2022',
            vehicle_colour='White', license_plate_number='LAG-123',
        )
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_provider_approval_detail', args=[profile.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('eligibility', response.data)
        self.assertIn('documents', response.data)
        self.assertIn('checks', response.data['eligibility'])
        self.assertGreater(response.data['eligibility']['total'], 0)
        self.assertIsInstance(response.data['documents'], list)

    # ── Approve clears previous rejection reason ───────────────────────────
    def test_approve_clears_rejection_reason(self):
        profile = self._chaperone()
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_process_provider_approval', args=[profile.id])

        self.client.post(url, {'action': 'reject', 'notes': 'Bad docs'}, format='json')
        profile.refresh_from_db()
        self.assertEqual(profile.rejection_reason, 'Bad docs')

        self.client.post(url, {'action': 'approve'}, format='json')
        profile.refresh_from_db()
        self.assertEqual(profile.rejection_reason, '')
        self.assertEqual(profile.approval_status, 'approved')

    # ── Service type filter ─────────────────────────────────────────────────
    def test_service_type_filter(self):
        d = self._driver('drv')
        c = self._chaperone('chap')
        self.client.force_authenticate(user=self.admin)

        resp = self.client.get(reverse('admin_providers_all'), {'service_type': 'airport_pickup'}).data
        results = _extract_list(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['service_type'], 'airport_pickup')

        resp = self.client.get(reverse('admin_providers_all'), {'service_type': 'chaperone'}).data
        results = _extract_list(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['service_type'], 'chaperone')
