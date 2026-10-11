import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial deployment administrator from environment secrets, if absent."

    def handle(self, *args, **options):
        username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "").strip()
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        if not username or not password:
            raise CommandError("Set BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD in the hosting environment.")

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS("Initial admin account created."))
        elif not (user.is_staff and user.is_superuser):
            raise CommandError("The configured bootstrap username exists but is not an administrator.")
        else:
            self.stdout.write("Initial admin account already exists; credentials were left unchanged.")
