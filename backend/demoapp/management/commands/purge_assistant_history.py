from django.core.management.base import BaseCommand
from django.utils import timezone

from demoapp.models import AssistantConversation


class Command(BaseCommand):
    help = 'Delete expired assistant conversations and their turns/tool results (30-day retention).'

    def handle(self, *args, **options):
        count, _ = AssistantConversation.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f'Deleted {count} expired history rows (including related rows).')
