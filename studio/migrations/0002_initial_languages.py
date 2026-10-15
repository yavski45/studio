from django.db import migrations


def seed_languages(apps, schema_editor):
    Language = apps.get_model('studio', 'DubbingLanguage')
    # Première sélection issue du guide Murf Dub. sync_murf_languages actualise
    # ensuite le catalogue à partir des endpoints du compte utilisé.
    for locale, name in [
        ('fr_FR', 'Français'), ('en_US', 'Anglais (États-Unis)'),
        ('en_UK', 'Anglais (Royaume-Uni)'), ('de_DE', 'Allemand'),
        ('es_ES', 'Espagnol (Espagne)'), ('es_MX', 'Espagnol (Mexique)'),
        ('it_IT', 'Italien'), ('pt_BR', 'Portugais (Brésil)'),
        ('ja_JP', 'Japonais'), ('zh_CN', 'Chinois (mandarin)'),
        ('nl_NL', 'Néerlandais'), ('hi_IN', 'Hindi'), ('ko_KR', 'Coréen'),
    ]:
        Language.objects.using(schema_editor.connection.alias).get_or_create(
            locale=locale, defaults={'name': name, 'source': True, 'target': True},
        )


class Migration(migrations.Migration):
    dependencies = [('studio', '0001_initial')]
    operations = [migrations.RunPython(seed_languages, migrations.RunPython.noop)]
