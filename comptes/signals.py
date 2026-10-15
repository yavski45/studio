import logging

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Profile


logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='comptes.create_user_profile')
def create_user_profile(sender, instance, created, raw, using, **kwargs):
    if created and not raw:
        Profile.objects.using(using).get_or_create(user_id=instance.pk)


def delete_avatar_after_commit(storage, name, using=None):
    if not name:
        return

    def delete_file():
        try:
            storage.delete(name)
        except (BotoCoreError, ClientError, OSError) as error:
            logger.warning('Suppression de photo indisponible : %s', type(error).__name__)

    transaction.on_commit(delete_file, using=using)


@receiver(post_delete, sender=Profile, dispatch_uid='comptes.delete_profile_avatar')
def delete_profile_avatar(sender, instance, using, **kwargs):
    delete_avatar_after_commit(instance.avatar.storage, instance.avatar.name, using)

