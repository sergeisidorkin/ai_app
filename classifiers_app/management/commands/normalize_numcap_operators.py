import re

from django.core.management.base import BaseCommand
from django.db import transaction

from classifiers_app.models import NumcapRecord


BATCH_SIZE = 5000


def _normalize_guillemets(value):
    text = value or ""
    if '"' not in text:
        return text
    out = []
    for char in text:
        if char == '"':
            prev = out[-1] if out else ""
            out.append("\u00AB" if (not prev or re.match(r"[\s(\[{\u00AB]", prev)) else "\u00BB")
        else:
            out.append(char)
    return "".join(out)


class Command(BaseCommand):
    help = "Нормализует поле operator в numcap, заменяя прямые кавычки на кавычки-елочки."

    def handle(self, *args, **options):
        queryset = NumcapRecord.objects.filter(operator__contains='"').only("id", "operator").order_by("id")
        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Записи numcap с прямыми кавычками не найдены."))
            return

        self.stdout.write(f"Найдено записей для нормализации: {total}")
        processed = 0
        updated = 0
        batch = []

        def flush():
            nonlocal updated
            if not batch:
                return
            with transaction.atomic():
                NumcapRecord.objects.bulk_update(batch, ["operator"], batch_size=BATCH_SIZE)
            updated += len(batch)
            batch.clear()

        for item in queryset.iterator(chunk_size=BATCH_SIZE):
            normalized = _normalize_guillemets(item.operator)
            processed += 1
            if normalized != item.operator:
                item.operator = normalized
                batch.append(item)
            if processed % BATCH_SIZE == 0:
                flush()
                self.stdout.write(f"Обработано: {processed} из {total}, обновлено: {updated}")
                self.stdout.flush()

        flush()
        self.stdout.write(self.style.SUCCESS(f"Готово. Обработано: {processed}, обновлено: {updated}."))
