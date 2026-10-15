from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('credits', '0007_creditpurchase_quoted_at')]
    operations = [migrations.AddField(
        model_name='creditpurchase', name='quoted_amount',
        field=models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True),
    )]
