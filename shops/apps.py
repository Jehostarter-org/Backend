import os
from django.apps import AppConfig
from django.conf import settings


class ShopsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "shops"

    def ready(self):
        upload_dirs = [
            "listing_images",
            "avatars",
            "vehicle_photos",
            "plate_photos",
            "driver_licenses",
            "eligibility_documents",
            "community_attachments",
            "community_covers",
        ]
        for d in upload_dirs:
            os.makedirs(os.path.join(settings.MEDIA_ROOT, d), exist_ok=True)
