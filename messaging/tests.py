from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.test import TestCase

from .presence import _mark_online, _mark_offline, user_is_online
from .models import Conversation
from .serializers import ParticipantSerializer

User = get_user_model()


class PresenceTests(TestCase):
    """Online/offline state is the single source used by REST + WS presence."""

    def setUp(self):
        cache.clear()
        self.u1 = User.objects.create_user(username='alice', email='alice@example.com')
        self.u2 = User.objects.create_user(username='bob', email='bob@example.com')

    def test_user_starts_offline(self):
        self.assertTrue(cache.get('presence:online:nope') is None)
        self.assertFalse(user_is_online(self.u1.pk))

    def test_mark_online_sets_presence(self):
        # First heartbeat -> was offline, now online.
        self.assertFalse(_mark_online(self.u1.pk))
        self.assertTrue(user_is_online(self.u1.pk))

    def test_mark_online_second_heartbeat_is_idempotent(self):
        # Repeated pings must not re-announce the transition.
        _mark_online(self.u1.pk)
        self.assertTrue(_mark_online(self.u1.pk))

    def test_mark_offline_clears_presence(self):
        _mark_online(self.u1.pk)
        self.assertTrue(_mark_offline(self.u1.pk))
        self.assertFalse(user_is_online(self.u1.pk))

    def test_mark_offline_when_already_offline_is_noop(self):
        self.assertFalse(_mark_offline(self.u1.pk))

    def test_online_state_is_per_user(self):
        _mark_online(self.u1.pk)
        self.assertTrue(user_is_online(self.u1.pk))
        self.assertFalse(user_is_online(self.u2.pk))

    def test_participant_serializer_reports_live_online_state(self):
        conversation = Conversation.objects.create()
        conversation.participants.set([self.u1, self.u2])

        _mark_online(self.u2.pk)
        self.assertTrue(ParticipantSerializer(self.u2, context={}).data['is_online'])

        _mark_offline(self.u2.pk)
        self.assertFalse(ParticipantSerializer(self.u2, context={}).data['is_online'])