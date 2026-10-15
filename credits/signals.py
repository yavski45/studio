from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CreditWallet


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='credits.create_wallet')
def create_wallet(sender, instance, created, raw, using, **kwargs):
    if created and not raw:
        CreditWallet.objects.using(using).get_or_create(user_id=instance.pk)
