"""
Project-wide Django admin tweaks.

Imported from backend.urls so every ModelAdmin gets superuser-friendly editing
and the admin site shows a consistent title.
"""
from django.contrib import admin

admin.site.site_header = 'Jehostarter Admin'
admin.site.site_title = 'Jehostarter'
admin.site.index_title = 'Platform management'

# Fields that should stay read-only even for superusers (IDs, timestamps, computed).
SYSTEM_READONLY = frozenset({
    'id', 'created_at', 'updated_at', 'date_joined', 'last_login',
    'submitted_at', 'reviewed_at', 'uploaded_at', 'verified_at',
    'used_at', 'resolved_at', 'flagged_at', 'deleted_at', 'banned_at',
    'approved_at', 'registered_at', 'read_at', 'saved_at', 'started_at',
    'latitude', 'longitude', 'rating', 'total_reviews', 'member_count',
    'post_count', 'like_count', 'comment_count', 'token',
})

DISPLAY_READONLY_SUFFIXES = (
    '_preview', '_link', '_display', '_badge', '_short', '_info', '_thumbnail',
)


def _is_display_only_field(name):
    return name.endswith(DISPLAY_READONLY_SUFFIXES)


_original_get_readonly_fields = admin.ModelAdmin.get_readonly_fields


def _superuser_friendly_readonly_fields(self, request, obj=None):
    readonly = list(_original_get_readonly_fields(self, request, obj))
    if not request.user.is_superuser:
        return readonly
    return [
        name for name in readonly
        if name in SYSTEM_READONLY or _is_display_only_field(name)
    ]


admin.ModelAdmin.get_readonly_fields = _superuser_friendly_readonly_fields
