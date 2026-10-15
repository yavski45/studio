from django.conf import settings
from django.db import migrations


def create_existing_profiles(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Profile = apps.get_model('comptes', 'Profile')
    alias = schema_editor.connection.alias
    user_ids = User.objects.using(alias).filter(profile__isnull=True).values_list('pk', flat=True)
    for user_id in user_ids.iterator(chunk_size=1000):
        Profile.objects.using(alias).get_or_create(user_id=user_id)


class Migration(migrations.Migration):
    dependencies = [('comptes', '0001_initial')]
    operations = [migrations.RunPython(create_existing_profiles, migrations.RunPython.noop)]
