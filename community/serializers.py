from rest_framework import serializers
from .models import Community, CommunityMember, Post, PostImage, Comment, PostLike, PostReport, Message


class CommunitySerializer(serializers.ModelSerializer):
    member_count     = serializers.ReadOnlyField()
    creator_username = serializers.ReadOnlyField(source='creator.username')
    is_member        = serializers.SerializerMethodField()

    class Meta:
        model  = Community
        fields = [
            'id', 'name', 'slug', 'description', 'creator', 'creator_username',
            'country_code', 'visibility', 'cover_image', 'is_active',
            'purpose', 'rules', 'member_count', 'post_count', 'is_member', 'created_at',
        ]
        read_only_fields = ['id', 'creator', 'slug', 'created_at']

    def get_is_member(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.members.filter(user=request.user).exists()
        return False


class CommunityMemberSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model  = CommunityMember
        fields = ['id', 'user', 'username', 'role', 'joined_at']
        read_only_fields = ['id', 'joined_at']


class PostImageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PostImage
        fields = ['id', 'image','caption', 'order']


class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.ReadOnlyField(source='author.username')
    replies         = serializers.SerializerMethodField()

    class Meta:
        model  = Comment
        fields = ['id', 'author', 'author_username', 'parent', 'content', 'replies', 'created_at']
        read_only_fields = ['id', 'author', 'created_at']

    def get_replies(self, obj):
        if obj.parent is None:
            return CommentSerializer(obj.replies.filter(is_deleted=False), many=True, context=self.context).data
        return []


class PostSerializer(serializers.ModelSerializer):
    images          = PostImageSerializer(many=True, read_only=True)
    comments_count  = serializers.ReadOnlyField(source='comment_count')
    likes_count     = serializers.ReadOnlyField(source='like_count')
    is_liked        = serializers.SerializerMethodField()
    author_username = serializers.ReadOnlyField(source='author.username')

    class Meta:
        model  = Post
        fields = [
            'id', 'community', 'author', 'author_username',
            'post_type', 'content', 'video_url', 'video_title', 'video_thumbnail',
            'shop_listing', 'is_approved', 'images',
            'comments_count', 'likes_count', 'is_liked', 'created_at',
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


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.ReadOnlyField(source='sender.username')
    sender_avatar   = serializers.SerializerMethodField()

    class Meta:
        model  = Message
        fields = ['id', 'community', 'sender', 'sender_username', 'sender_avatar', 'content', 'created_at']
        read_only_fields = ['id', 'sender', 'created_at']

    def get_sender_avatar(self, obj):
        request = self.context.get('request')
        avatar = getattr(obj.sender, 'avatar', None) or getattr(obj.sender, 'profile_picture', None)
        if avatar and request:
            return request.build_absolute_uri(avatar.url)
        return None