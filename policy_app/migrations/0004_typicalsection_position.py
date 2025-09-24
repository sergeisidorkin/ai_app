from django.db import migrations, models

def init_positions(apps, schema_editor):
    TypicalSection = apps.get_model('policy_app', 'TypicalSection')
    db_alias = schema_editor.connection.alias
    # Заполняем позициями внутри каждого продукта по текущему упорядочиванию (product_id, id)
    qs = TypicalSection.objects.using(db_alias).all().order_by('product_id', 'id')
    current_pid = None
    pos = 0
    for sec in qs:
        if sec.product_id != current_pid:
            current_pid = sec.product_id
            pos = 0
        pos += 1
        TypicalSection.objects.using(db_alias).filter(pk=sec.pk).update(position=pos)

class Migration(migrations.Migration):

    dependencies = [
        ('policy_app', '0003_alter_product_options_product_position'),
    ]

    operations = [
        migrations.AddField(
            model_name='typicalsection',
            name='position',
            field=models.PositiveIntegerField(db_index=True, default=0, verbose_name='Позиция'),
        ),
        migrations.RunPython(init_positions, migrations.RunPython.noop),
    ]