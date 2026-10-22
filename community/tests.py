"""Tests for community join-request notifications: admin alerting on join,
Accept/Decline side effects (approve/reject), and the open-community path."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from notifications.models import Notification

from .models import Community, CommunityMember, CommunityInvite

User = get_user_model()


class JoinRequestNotificationTests(APITestCase):
    """Joining an approval-required community must leave an actionable
    Notification on every admin's notification page — the notification page
    reads `data.community_id` / `data.member_id` to call approve/reject."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='admin1', password='pass')
        self.mod = User.objects.create_user(username='mod1', password='pass')
        self.bystander = User.objects.create_user(username='bystander1', password='pass')
        self.banned_admin = User.objects.create_user(username='bannedadmin', password='pass')
        self.joiner = User.objects.create_user(username='joiner1', password='pass')

        self.community = Community.objects.create(
            name='Nigerians in Brisbane',
            slug='nigerians-in-brisbane',
            description='Diaspora group',
            creator=self.admin,
            require_approval=True,
        )
        CommunityMember.objects.create(
            community=self.community, user=self.admin, role='admin', status='approved',
        )
        CommunityMember.objects.create(
            community=self.community, user=self.mod, role='moderator', status='approved',
        )
        CommunityMember.objects.create(
            community=self.community, user=self.bystander, role='member', status='approved',
        )
        CommunityMember.objects.create(
            community=self.community, user=self.banned_admin, role='admin',
            status='approved', is_banned=True,
        )

        self.client.force_authenticate(user=self.joiner)
        self.join_url = reverse('join_community', args=[self.community.pk])

    # ── Pending join: admins get notified ───────────────────────────────────
    def test_join_pending_notifies_admin_and_moderator_only(self):
        resp = self.client.post(self.join_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'pending')

        notifications = Notification.objects.filter(
            notification_type='community_join_request',
        )
        recipients = set(notifications.values_list('recipient_id', flat=True))
        # plain member and banned admin must not be alerted
        self.assertEqual(recipients, {self.admin.pk, self.mod.pk})

        member = CommunityMember.objects.get(community=self.community, user=self.joiner)
        self.assertEqual(member.status, 'pending')

        notif = notifications.get(recipient=self.admin)
        self.assertEqual(notif.actor, self.joiner)
        self.assertEqual(notif.data['community_id'], str(self.community.pk))
        self.assertEqual(notif.data['member_id'], str(member.pk))
        self.assertEqual(notif.data['username'], self.joiner.username)
        self.assertIn(self.joiner.username, notif.title)
        self.assertFalse(notif.is_read)

    def test_join_repeated_while_pending_creates_single_notification(self):
        self.client.post(self.join_url)
        resp = self.client.post(self.join_url)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            Notification.objects.filter(
                notification_type='community_join_request', recipient=self.admin,
            ).count(),
            1,
        )

    # ── Open community: no approval, no notification ────────────────────────
    def test_open_community_join_is_immediate_and_silent(self):
        self.community.require_approval = False
        self.community.save(update_fields=['require_approval'])

        resp = self.client.post(self.join_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(resp.data.get('status'), 'pending')

        member = CommunityMember.objects.get(community=self.community, user=self.joiner)
        self.assertEqual(member.status, 'approved')
        self.assertIsNotNone(member.approved_at)
        self.assertFalse(
            Notification.objects.filter(notification_type='community_join_request').exists()
        )


class ApproveRejectNotificationTests(APITestCase):
    """Approving/rejecting from the notification page must: change membership,
    clear the admins' pending-request notifications, and tell the applicant."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='admin2', password='pass')
        self.other_admin = User.objects.create_user(username='admin3', password='pass')
        self.joiner = User.objects.create_user(username='joiner2', password='pass')

        self.community = Community.objects.create(
            name='UK Job Seekers',
            slug='uk-job-seekers',
            description='Jobs',
            creator=self.admin,
            require_approval=True,
        )
        for user in (self.admin, self.other_admin):
            CommunityMember.objects.create(
                community=self.community, user=user, role='admin', status='approved',
            )

        self.client.force_authenticate(user=self.joiner)
        self.client.post(reverse('join_community', args=[self.community.pk]))
        self.member = CommunityMember.objects.get(community=self.community, user=self.joiner)

        # act as an admin from here on
        self.client.force_authenticate(user=self.admin)
        self.approve_url = reverse('approve_member', args=[self.community.pk, self.member.pk])
        self.reject_url = reverse('reject_member', args=[self.community.pk, self.member.pk])

    def _admin_notifications(self):
        return Notification.objects.filter(
            notification_type='community_join_request',
            recipient__in=[self.admin, self.other_admin],
        )

    # ── Approve ─────────────────────────────────────────────────────────────
    def test_approve_clears_admin_notifications_and_informs_joiner(self):
        self.assertEqual(self._admin_notifications().filter(is_read=False).count(), 2)

        resp = self.client.post(self.approve_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.member.refresh_from_db()
        self.assertEqual(self.member.status, 'approved')
        self.assertIsNotNone(self.member.approved_at)

        # every admin's pending row is now read (no stale Accept/Decline)
        for notif in self._admin_notifications():
            self.assertTrue(notif.is_read)
            self.assertIsNotNone(notif.read_at)

        result = Notification.objects.get(
            recipient=self.joiner, notification_type='community_join_result',
        )
        self.assertTrue(result.data['approved'])
        self.assertIn('approved', result.message)

    # ── Reject ──────────────────────────────────────────────────────────────
    def test_reject_clears_admin_notifications_and_informs_joiner(self):
        resp = self.client.post(self.reject_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.member.refresh_from_db()
        self.assertEqual(self.member.status, 'rejected')

        self.assertFalse(self._admin_notifications().filter(is_read=False).exists())

        result = Notification.objects.get(
            recipient=self.joiner, notification_type='community_join_result',
        )
        self.assertFalse(result.data['approved'])
        self.assertIn('rejected', result.message)

    # ── Access control & stale requests ─────────────────────────────────────
    def test_non_admin_cannot_approve(self):
        self.client.force_authenticate(user=self.joiner)

        resp = self.client.post(self.approve_url)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.member.refresh_from_db()
        self.assertEqual(self.member.status, 'pending')
        self.assertEqual(self._admin_notifications().filter(is_read=False).count(), 2)

    def test_approving_twice_returns_404(self):
        self.assertEqual(self.client.post(self.approve_url).status_code, status.HTTP_200_OK)

        resp = self.client.post(self.approve_url)

        # second admin clicking a stale notification gets a clean 404
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_reject_unknown_member_returns_404(self):
        resp = self.client.post(
            reverse('reject_member', args=[self.community.pk, 'doesnotexist']),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class RejectedRejoinTests(APITestCase):
    """A rejected applicant must be able to ask again. Previously join
    returned 'Already a member.' 400 and the UI pretended they were in."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='admin4', password='pass')
        self.joiner = User.objects.create_user(username='joiner4', password='pass')
        self.community = Community.objects.create(
            name='Melbourne Creatives',
            slug='melbourne-creatives',
            description='Art',
            creator=self.admin,
            require_approval=True,
        )
        CommunityMember.objects.create(
            community=self.community, user=self.admin, role='admin', status='approved',
        )
        self.rejected = CommunityMember.objects.create(
            community=self.community, user=self.joiner, status='rejected',
        )
        self.client.force_authenticate(user=self.joiner)
        self.join_url = reverse('join_community', args=[self.community.pk])

    def test_rejected_member_re_requests_on_approval_community(self):
        resp = self.client.post(self.join_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'pending')
        self.rejected.refresh_from_db()
        self.assertEqual(self.rejected.status, 'pending')
        self.assertTrue(
            Notification.objects.filter(
                notification_type='community_join_request',
                recipient=self.admin,
                is_read=False,
            ).exists()
        )

    def test_rejected_member_joins_open_community_immediately(self):
        self.community.require_approval = False
        self.community.save(update_fields=['require_approval'])

        resp = self.client.post(self.join_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(resp.data.get('status'), 'pending')
        self.rejected.refresh_from_db()
        self.assertEqual(self.rejected.status, 'approved')
        self.assertIsNotNone(self.rejected.approved_at)
        self.community.refresh_from_db()
        approved = CommunityMember.objects.filter(
            community=self.community, status='approved',
        ).count()
        self.assertEqual(self.community.member_count, approved)

    def test_banned_rejected_member_still_blocked(self):
        self.rejected.is_banned = True
        self.rejected.save(update_fields=['is_banned'])

        resp = self.client.post(self.join_url)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_approved_member_join_still_returns_400(self):
        CommunityMember.objects.filter(pk=self.rejected.pk).update(status='approved')

        resp = self.client.post(self.join_url)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['detail'], 'Already a member.')


class MemberCountTests(APITestCase):
    """member_count must track approved members only — leave/remove
    previously counted pending+rejected rows and inflated the count."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='admin5', password='pass')
        self.leaver = User.objects.create_user(username='leaver5', password='pass')
        self.pending_user = User.objects.create_user(username='pending5', password='pass')
        self.rejected_user = User.objects.create_user(username='rejected5', password='pass')
        self.community = Community.objects.create(
            name='Lagos Founders',
            slug='lagos-founders',
            description='Startups',
            creator=self.admin,
            require_approval=True,
        )
        CommunityMember.objects.create(
            community=self.community, user=self.admin, role='admin', status='approved',
        )
        CommunityMember.objects.create(
            community=self.community, user=self.leaver, status='approved',
        )
        CommunityMember.objects.create(
            community=self.community, user=self.pending_user, status='pending',
        )
        CommunityMember.objects.create(
            community=self.community, user=self.rejected_user, status='rejected',
        )

    def test_leave_recounts_approved_only(self):
        self.client.force_authenticate(user=self.leaver)

        resp = self.client.delete(reverse('leave_community', args=[self.community.pk]))

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.community.refresh_from_db()
        self.assertEqual(self.community.member_count, 1)

    def test_admin_remove_recounts_approved_only(self):
        self.client.force_authenticate(user=self.admin)

        resp = self.client.delete(
            reverse('remove_member', args=[self.community.pk, self.leaver.pk]),
        )

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.community.refresh_from_db()
        self.assertEqual(self.community.member_count, 1)


class InviteRejoinTests(APITestCase):
    """Invite links had the same rejected-block bug, a dead banned check,
    and never notified admins when they created a pending request."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username='admin6', password='pass')
        self.joiner = User.objects.create_user(username='joiner6', password='pass')
        self.community = Community.objects.create(
            name='Paris Expats',
            slug='paris-expats',
            description='Expats',
            creator=self.admin,
            require_approval=True,
        )
        CommunityMember.objects.create(
            community=self.community, user=self.admin, role='admin', status='approved',
        )
        self.invite = CommunityInvite.objects.create(
            community=self.community,
            invited_by=self.admin,
            token='tok123',
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_authenticate(user=self.joiner)
        self.accept_url = reverse('accept_invite', args=[self.invite.token])

    def test_fresh_invite_pending_notifies_admins_and_marks_invite_used(self):
        resp = self.client.post(self.accept_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'pending')
        member = CommunityMember.objects.get(community=self.community, user=self.joiner)
        self.assertEqual(member.status, 'pending')
        self.invite.refresh_from_db()
        self.assertTrue(self.invite.used)
        self.assertTrue(
            Notification.objects.filter(
                notification_type='community_join_request',
                recipient=self.admin,
                is_read=False,
            ).exists()
        )

    def test_rejected_member_can_re_join_via_invite(self):
        CommunityMember.objects.create(
            community=self.community, user=self.joiner, status='rejected',
        )

        resp = self.client.post(self.accept_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'pending')
        member = CommunityMember.objects.get(community=self.community, user=self.joiner)
        self.assertEqual(member.status, 'pending')

    def test_banned_member_invite_returns_403(self):
        CommunityMember.objects.create(
            community=self.community, user=self.joiner, status='rejected', is_banned=True,
        )

        resp = self.client.post(self.accept_url)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
