from django.db import migrations


def backfill(apps, schema_editor):
    RequestTable = apps.get_model('requests_app', 'RequestTable')
    RequestItem = apps.get_model('requests_app', 'RequestItem')
    Product = apps.get_model('policy_app', 'Product')
    TypicalSection = apps.get_model('policy_app', 'TypicalSection')

    db = schema_editor.connection.alias

    # Нужен любой продукт, т.к. RequestTable.product NOT NULL
    product = Product.objects.using(db).first()
    if product is None:
        # Нет продуктов — ничего не делаем (оставим NULL, пока не появится продукт)
        return

    # Берём существующую таблицу или создаём одну базовую
    table = RequestTable.objects.using(db).first()
    if table is None:
        kwargs = {'product_id': product.id}

        # Если у RequestTable есть поле section — попробуем подставить любую секцию (или None, если оно nullable)
        try:
            RequestTable._meta.get_field('section')
            section = (
                TypicalSection.objects.using(db)
                .filter(product_id=product.id)
                .first()
                or TypicalSection.objects.using(db).first()
            )
            # даже если section None — ок, если поле допускает NULL
            kwargs['section_id'] = section.id if section else None
        except Exception:
            # поля section нет — игнорируем
            pass

        table = RequestTable.objects.using(db).create(**kwargs)

    # Проставляем ссылку всем старым строкам
    RequestItem.objects.using(db).filter(table__isnull=True).update(table_id=table.id)


class Migration(migrations.Migration):
    dependencies = [
        ('requests_app', '0004_requesttable_alter_requestitem_options_and_more'),
        # На всякий случай гарантируем, что таблицы продуктов и секций уже есть
        ('policy_app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]