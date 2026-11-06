"""Хранимая частота блока в составе продуктов.

Показатель — число строк «Типовые блоки услуг» с этим блоком. Считается
заранее, чтобы выпадающий список кода не делал COUNT при каждом открытии.
"""

def sync_service_block_usage_counts(block_ids):
    ids = {block_id for block_id in block_ids if block_id}
    if not ids:
        return

    from django.db.models import Count

    from policy_app.models import ServiceBlockClassifier, TypicalSection

    counts = {
        row["service_block_id"]: row["total"]
        for row in (
            TypicalSection.objects.filter(service_block_id__in=ids)
            .values("service_block_id")
            .annotate(total=Count("pk"))
        )
    }
    for block_id in ids:
        ServiceBlockClassifier.objects.filter(pk=block_id).update(
            usage_count=counts.get(block_id, 0)
        )
