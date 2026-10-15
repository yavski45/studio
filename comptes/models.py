from django.utils.translation import gettext_lazy
from pathlib import PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


def avatar_upload_path(instance, filename):
    extension = PurePosixPath(filename).suffix.lower()
    return f'profiles/{instance.user_id}/{uuid4().hex}{extension}'


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='profile', verbose_name=gettext_lazy('utilisateur'),
    )
    bio = models.TextField(gettext_lazy('biographie'), blank=True, max_length=500)
    avatar = models.ImageField(
        gettext_lazy('photo de profil'), upload_to=avatar_upload_path, blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
    )
    created_at = models.DateTimeField(gettext_lazy('créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy('modifié le'), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy('profil utilisateur')
        verbose_name_plural = gettext_lazy('profils utilisateurs')

    def __str__(self):
        return self.user.get_full_name() or self.user.email or self.user.get_username()
