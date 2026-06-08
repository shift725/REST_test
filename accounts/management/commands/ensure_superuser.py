"""
從 DJANGO_SUPERUSER_* 環境變數冪等地建立／升級 superuser，並設定 role='admin'。

容器啟動時由 docker/entrypoint.sh 呼叫；三個 env var 任一未設則完全跳過，
讓本機不想自動建 admin 的人也能正常啟動。
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Idempotently create or upgrade a superuser with role='admin' from env vars."

    def handle(self, *args, **options):
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')

        if not (email and username and password):
            self.stdout.write('DJANGO_SUPERUSER_* not fully set; skipping.')
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': username,
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            },
        )

        if created:
            user.set_password(password)
            user.save(update_fields=['password'])
            self.stdout.write(self.style.SUCCESS(f'Created superuser {email} (role=admin)'))
            return

        # 既有使用者：補齊 admin 旗標但不覆蓋密碼（避免 .env 改動意外重置線上密碼）
        changed = []
        if user.role != 'admin':
            user.role = 'admin'
            changed.append('role')
        if not user.is_staff:
            user.is_staff = True
            changed.append('is_staff')
        if not user.is_superuser:
            user.is_superuser = True
            changed.append('is_superuser')

        if changed:
            user.save(update_fields=changed)
            self.stdout.write(self.style.SUCCESS(f'Upgraded {email}: {", ".join(changed)} updated'))
        else:
            self.stdout.write(f'Superuser {email} already correct; no change.')
