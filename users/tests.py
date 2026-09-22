"""Tests for admin user management: suspend/unsuspend, user list, serializer fields."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

User = get_user_model()


class AdminSuspendUnsuspendTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin1', password='pass', is_staff=True,
        )
        self.user = User.objects.create_user(
            username='member1', password='pass', email='member@test.com',
        )

    # ── Access control ──────────────────────────────────────────────────────
    def test_anonymous_cannot_suspend(self):
        url = reverse('admin_toggle_user_active', args=[self.user.id])
        response = self.client.post(url, format='json')
        self.assertIn(response.status_code, [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ])

    def test_non_admin_cannot_suspend(self):
        regular = User.objects.create_user(username='regular', password='pass')
        self.client.force_authenticate(user=regular)
        url = reverse('admin_toggle_user_active', args=[self.user.id])
        response = self.client.post(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── Suspend a user ─────────────────────────────────────────────────────
    def test_admin_suspend_user(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_toggle_user_active', args=[self.user.id])
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])
        self.assertIn('suspended', response.data['message'].lower())

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    # ── Unsuspend a user ───────────────────────────────────────────────────
    def test_admin_unsuspend_user(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_toggle_user_active', args=[self.user.id])
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_active'])
        self.assertIn('activated', response.data['message'].lower())

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    # ── Double toggle (suspend → unsuspend) ────────────────────────────────
    def test_double_toggle(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_toggle_user_active', args=[self.user.id])

        resp1 = self.client.post(url, format='json')
        self.assertFalse(resp1.data['is_active'])

        resp2 = self.client.post(url, format='json')
        self.assertTrue(resp2.data['is_active'])

    # ── Cannot suspend admin accounts ──────────────────────────────────────
    def test_cannot_suspend_admin_account(self):
        other_admin = User.objects.create_user(
            username='admin2', password='pass', is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_toggle_user_active', args=[other_admin.id])
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('admin', response.data['detail'].lower())

        other_admin.refresh_from_db()
        self.assertTrue(other_admin.is_active)

    # ── Suspended user cannot log in ───────────────────────────────────────
    def test_suspended_user_cannot_login(self):
        self.user.set_password('testpass123')
        self.user.save(update_fields=['password'])

        # Suspend
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_toggle_user_active', args=[self.user.id])
        self.client.post(url, format='json')

        # Try to login
        self.client.force_authenticate(user=None)
        login_url = reverse('login')
        response = self.client.post(login_url, {
            'username': 'member@test.com',
            'password': 'testpass123',
        }, format='json')
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    # ── 404 for non-existent user ──────────────────────────────────────────
    def test_nonexistent_user_returns_404(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_toggle_user_active', args=['nonexistent123'])
        response = self.client.post(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminUserListSerializerTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin1', password='pass', is_staff=True,
        )
        self.user = User.objects.create_user(
            username='member1', password='pass', email='member@test.com',
            first_name='Test', last_name='User',
            city='Lagos', current_country='NG',
            accepted_terms=True, accepted_terms_at=timezone.now(),
        )

    # ── is_active in list response ─────────────────────────────────────────
    def test_user_list_includes_is_active(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_users_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data if isinstance(response.data, list) else response.data.get('results', [])
        self.assertTrue(len(results) > 0)
        user_data = next(u for u in results if u['id'] == self.user.id)
        self.assertIn('is_active', user_data)
        self.assertTrue(user_data['is_active'])

    # ── is_active in detail response ───────────────────────────────────────
    def test_user_detail_includes_is_active(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_user_detail', args=[self.user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('is_active', response.data)
        self.assertTrue(response.data['is_active'])

    # ── accepted_terms_at in response ──────────────────────────────────────
    def test_user_detail_includes_accepted_terms_at(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_user_detail', args=[self.user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('accepted_terms_at', response.data)
        self.assertIsNotNone(response.data['accepted_terms_at'])

    # ── suspended user shows is_active=false in list ───────────────────────
    def test_suspended_user_shows_inactive_in_list(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        self.client.force_authenticate(user=self.admin)
        url = reverse('admin_users_list')
        response = self.client.get(url)

        results = response.data if isinstance(response.data, list) else response.data.get('results', [])
        user_data = next(u for u in results if u['id'] == self.user.id)
        self.assertFalse(user_data['is_active'])
