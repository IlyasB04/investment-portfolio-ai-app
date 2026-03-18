import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        """
        Start the market price simulator when Django is ready to serve requests.

        Guard logic
        -----------
        Django's autoreloader starts TWO processes:
          1. The monitor/parent process — watches files, no RUN_MAIN env var.
          2. The child process          — actually serves HTTP, RUN_MAIN=true.

        We must not start the scheduler in the parent process because it has
        no request handlers and creating threads in it causes resource waste
        and confusing log output.

        In non-devserver contexts (gunicorn, uvicorn, production WSGI/ASGI)
        there is no autoreloader, so RUN_MAIN is never set — we always start.

        Management commands that do not serve HTTP (migrate, shell, etc.) are
        excluded by checking sys.argv[1].
        """
        _SKIP_COMMANDS = {
            "migrate", "makemigrations", "createsuperuser",
            "shell", "test", "collectstatic", "check",
        }

        # Skip non-serving management commands
        current_command = sys.argv[1] if len(sys.argv) > 1 else ""
        if current_command in _SKIP_COMMANDS:
            return

        # When running devserver: only start in the child process (RUN_MAIN=true).
        # The parent reloader process does NOT have RUN_MAIN set.
        is_devserver = current_command == "runserver"
        is_reloader_parent = is_devserver and os.environ.get("RUN_MAIN") != "true"
        if is_reloader_parent:
            logger.debug("[CoreConfig] Autoreloader parent — skipping simulator")
            return

        try:
            from .simulator import start_scheduler
            start_scheduler()
        except Exception as exc:
            # Log but never crash Django startup
            logger.exception("[CoreConfig] Failed to start price simulator: %s", exc)
