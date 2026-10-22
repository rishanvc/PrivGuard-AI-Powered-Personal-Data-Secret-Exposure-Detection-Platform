from pathlib import Path

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"

    def ready(self):
        # Create the runtime folders under VAR_ROOT (NFR-023). Django requires
        # FILE_UPLOAD_TEMP_DIR to exist before the first large upload arrives,
        # and failing on that upload would be a confusing first error.
        from django.conf import settings

        for folder in (
            settings.UPLOAD_ROOT,
            settings.EXTRACTED_ROOT,
            settings.REDACTED_ROOT,
            settings.REPORT_ROOT,
            settings.TMP_ROOT,
        ):
            Path(folder).mkdir(parents=True, exist_ok=True)
