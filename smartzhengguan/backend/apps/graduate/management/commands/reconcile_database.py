import json
from pathlib import Path
from uuid import uuid4
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from apps.graduate.data_reconciliation import reconcile

class Command(BaseCommand):
    help='Reconcile verified demo records with recoverable archives; dry-run by default'
    def add_arguments(self, parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--report',type=Path)
        parser.add_argument('--batch-id',default='')
    def handle(self,*args,**options):
        try:
            result=reconcile(apply=options['apply'],batch_id=options['batch_id'] or ('repair-'+uuid4().hex[:16]))
        except ValidationError as exc:
            raise CommandError(str(exc))
        if options['report']:options['report'].write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        self.stdout.write(json.dumps(result,ensure_ascii=False))
