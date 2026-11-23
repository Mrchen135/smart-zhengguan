from django.core.management.base import BaseCommand, CommandError

from apps.employmenthub.collectors import CollectionError, run_sync, stop_watcher, watch_sources
from apps.employmenthub.models import EmploymentSource


class Command(BaseCommand):
    help = "Read bounded public recruitment pages once, or watch every 12 hours. Never sends student data."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Keep a single scheduler alive; first run starts immediately")
        parser.add_argument("--once", action="store_true", help="Run once (the default)")
        parser.add_argument("--stop", action="store_true", help="Ask the existing scheduler to stop gracefully")
        parser.add_argument("--interval", type=int, default=43200, help="Watch interval in seconds (minimum 600)")
        parser.add_argument("--source", help="Only read this configured source key in a single run")

    def handle(self, *args, **options):
        if options["stop"]:
            self.stdout.write(f"Stop requested for {stop_watcher()} scheduler(s); an in-progress bounded sync will finish first.")
            return
        if options["watch"] and (options["source"] or options["once"]):
            raise CommandError("--watch cannot be combined with --source or --once")
        try:
            if options["watch"]:
                self.stdout.write(f"Public recruitment scheduler started; interval {max(600, options['interval'])} seconds.")
                watch_sources(options["interval"])
                return
            source = None
            if options["source"]:
                source = EmploymentSource.objects.filter(key=options["source"], enabled=True).first()
                if source is None:
                    raise CommandError("Unknown or disabled source key")
            result = run_sync(source.pk if source else None)
            self.stdout.write(f"Run #{result.pk}: {result.status}; checked={result.checked_count}, created={result.created_count}, updated={result.updated_count}")
            if result.error:
                self.stderr.write(result.error)
            if result.status == "failed":
                raise CommandError("No source could be synchronized; previous records were retained")
        except CollectionError as error:
            raise CommandError(str(error)) from error
        except KeyboardInterrupt:
            self.stdout.write("Scheduler stopped.")
