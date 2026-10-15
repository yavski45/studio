from django.conf import settings
from django.db import migrations


def create_wallets(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    Wallet = apps.get_model('credits', 'CreditWallet')
    alias = schema_editor.connection.alias
    for user_id in User.objects.using(alias).values_list('pk', flat=True).iterator():
        Wallet.objects.using(alias).get_or_create(user_id=user_id)


class Migration(migrations.Migration):
    dependencies = [('credits', '0001_initial')]
    operations = [migrations.RunPython(create_wallets, migrations.RunPython.noop)]
