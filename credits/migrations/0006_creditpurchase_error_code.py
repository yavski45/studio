from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('credits', '0005_creditpurchase_refunded_at')]
    operations = [migrations.AddField(
        model_name='creditpurchase', name='error_code',
        field=models.CharField(max_length=40, blank=True),
    )]
