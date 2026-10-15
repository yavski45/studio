from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('credits', '0006_creditpurchase_error_code')]
    operations = [migrations.AddField(
        model_name='creditpurchase', name='quoted_at',
        field=models.DateTimeField(blank=True, null=True),
    )]
