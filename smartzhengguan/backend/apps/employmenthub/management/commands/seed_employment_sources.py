from django.core.management.base import BaseCommand

from apps.employmenthub.catalog import seed_sources


class Command(BaseCommand):
    help = "Initialize the verified public recruitment source registry (idempotent; no network)."

    def add_arguments(self, parser):
        parser.add_argument("--update-existing", action="store_true", help="Apply the current source registry to existing entries")

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Created {seed_sources(update_existing=options['update_existing'])} public source entries; registry updated={options['update_existing']}."))
