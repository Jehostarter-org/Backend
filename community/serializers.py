import os
import uuid

from django.core.files.storage import default_storage
from rest_framework import serializers
from .models import Community, CommunityMember, Post, PostImage, Comment, PostLike, PostReport, Message


class CommunitySerializer(serializers.ModelSerializer):
    member_count     = serializers.ReadOnlyField()
    creator_username = serializers.ReadOnlyField(source='creator.username')
    creator          = serializers.CharField(source='creator.pk', read_only=True)
    is_member        = serializers.SerializerMethodField()
    is_admin         = serializers.SerializerMethodField()
    require_approval = serializers.BooleanField(default=False)
    pending_count    = serializers.SerializerMethodField()
    my_status        = serializers.SerializerMethodField()

    class Meta:
        model  = Community
        fields = [
            'id', 'name', 'slug', 'description', 'creator', 'creator_username',
            'country_code', 'visibility', 'require_approval', 'cover_image', 'is_active',
            'purpose', 'rules', 'member_count', 'post_count',
            'is_member', 'is_admin', 'pending_count', 'my_status', 'created_at',
        ]
        read_only_fields = ['id', 'creator', 'slug', 'is_active', 'created_at']

    def get_is_member(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if getattr(obj, '_is_member', None) is not None:
                return bool(obj._is_member)
            if obj.creator_id == request.user.pk:
                return True
            return obj.members.filter(user=request.user, is_banned=False, status='approved').exists()
        return False

    def get_is_admin(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if getattr(obj, '_is_admin', None) is not None:
                return bool(obj._is_admin)
            if obj.creator_id == request.user.pk:
                return True
            return obj.members.filter(
                user=request.user,
                role__in=['admin', 'moderator'],
                is_banned=False,
                status='approved',
            ).exists()
        return False

    def get_pending_count(self, obj):
        return obj.members.filter(status='pending').count()

    def get_my_status(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            membership = obj.members.filter(user=request.user).first()
            if membership:
                return membership.status
        return None

    def _store_cover(self, instance, cover):
        ext = os.path.splitext(cover.name)[1].lower() or '.jpg'
        name = default_storage.save(f'community_attachments/{uuid.uuid4().hex}{ext}', cover)
        old = instance.cover_image
        if old and old.name != name:
            old.delete(save=False)
        instance.cover_image.name = name
        instance.save(update_fields=['cover_image', 'updated_at'])

    def create(self, validated_data):
        cover = validated_data.pop('cover_image', None)
        instance = super().create(validated_data)
        if cover:
            self._store_cover(instance, cover)
        return instance

    def update(self, instance, validated_data):
        cover = validated_data.pop('cover_image', None)
        instance = super().update(instance, validated_data)
        if cover:
            self._store_cover(instance, cover)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        cover = data.get('cover_image')
        if cover:
            request = self.context.get('request')
            if request:
                data['cover_image'] = request.build_absolute_uri(cover)
        return data


class CommunityMemberSerializer(serializers.ModelSerializer):
    username        = serializers.ReadOnlyField(source='user.username')
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model  = CommunityMember
        fields = ['id', 'user', 'username', 'profile_picture', 'role', 'status', 'joined_at', 'approved_at']
        read_only_fields = ['id', 'joined_at', 'approved_at']

    def get_profile_picture(self, obj):
        avatar = (
            getattr(obj.user, 'avatar', None)
            or getattr(obj.user, 'profile_picture', None)
        )
        if avatar and avatar.storage.exists(avatar.name):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(avatar.url)
            return avatar.url
        return None


class PostImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model  = PostImage
        fields = ['id', 'image', 'caption', 'order']

    def get_image(self, obj):
        if obj.image and obj.image.storage.exists(obj.image.name):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.ReadOnlyField(source='author.username')
    replies         = serializers.SerializerMethodField()

    class Meta:
        model  = Comment
        fields = ['id', 'author', 'author_username', 'parent', 'content', 'replies', 'created_at']
        read_only_fields = ['id', 'author', 'created_at']

    def get_replies(self, obj):
        if obj.parent is None:
            return CommentSerializer(
                obj.replies.filter(is_deleted=False), many=True, context=self.context
            ).data
        return []


class PostSerializer(serializers.ModelSerializer):
    images          = PostImageSerializer(many=True, read_only=True)
    comments_count  = serializers.ReadOnlyField(source='comment_count')
    likes_counts    = serializers.ReadOnlyField(source='like_count')
    is_liked        = serializers.SerializerMethodField()
    author_username = serializers.ReadOnlyField(source='author.username')

    class Meta:
        model  = Post
        fields = [
            'id', 'community', 'author', 'author_username',
            'post_type', 'content', 'video_url', 'video_title', 'video_thumbnail',
            'shop_listing', 'is_approved', 'images',
            'comments_count', 'likes_counts', 'is_liked', 'created_at',
        ]
        read_only_fields = ['id', 'author', 'is_approved', 'created_at']

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False


class PostReportSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PostReport
        fields = ['id', 'reason', 'detail', 'created_at']
        read_only_fields = ['id', 'created_at']


# ── Inline preview of the message being replied to ───────────────────────────

class ReplyToPreviewSerializer(serializers.ModelSerializer):
    sender_username = serializers.ReadOnlyField(source='sender.username')

    class Meta:
        model  = Message
        fields = ['id', 'sender_username', 'content']


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.ReadOnlyField(source='sender.username')
    sender_avatar   = serializers.SerializerMethodField()
    attachment_url  = serializers.SerializerMethodField()
    reply_to        = ReplyToPreviewSerializer(read_only=True)

    class Meta:
        model  = Message
        fields = [
            'id', 'community', 'sender', 'sender_username', 'sender_avatar',
            'content',
            'reply_to',
            'attachment', 'attachment_url', 'attachment_name',
            'attachment_type', 'attachment_size',
            'reactions', 'created_at',
        ]
        read_only_fields = ['reactions']
        read_only_fields = [
            'id', 'community', 'sender', 'attachment_name',
            'attachment_type', 'attachment_size', 'created_at',
        ]

    def get_sender_avatar(self, obj):
        avatar = (
            getattr(obj.sender, 'avatar', None)
            or getattr(obj.sender, 'profile_picture', None)
        )
        if avatar and avatar.storage.exists(avatar.name):
            request = self.context.get('request')
            if request:
                try:
                    return request.build_absolute_uri(avatar.url)
                except Exception:
                    pass
        return None

    def get_attachment_url(self, obj):
        if obj.attachment and obj.attachment.storage.exists(obj.attachment.name):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.attachment.url)
            return obj.attachment.url
        return None