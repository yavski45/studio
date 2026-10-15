from django.utils.translation import gettext_lazy
from io import BytesIO

from allauth.account import forms
from django import forms as django_forms
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from PIL import Image, ImageOps

from .models import Profile


INPUT_CLASS = (
    'block w-full rounded-xl border border-[#2b4035] bg-[#131e19] px-4 py-3 '
    'text-sm text-[#edf5f0] outline-none transition focus:border-[#60dda5] '
    'focus:ring-2 focus:ring-[#60dda5]/15'
)


class StyledFieldsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'remember':
                field.widget.attrs['class'] = 'h-4 w-4 rounded accent-[#60dda5]'
            else:
                field.widget.attrs['class'] = INPUT_CLASS
            if name in ('password', 'password1', 'password2'):
                field.widget.attrs.update({
                    'class': INPUT_CLASS + ' pr-20',
                    'x-bind:type': "showPassword ? 'text' : 'password'",
                })


class SignupForm(StyledFieldsMixin, forms.SignupForm):
    pass


class LoginForm(StyledFieldsMixin, forms.LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le lien de réinitialisation est affiché une seule fois par le template.
        self.fields['password'].help_text = ''


class ResetPasswordForm(StyledFieldsMixin, forms.ResetPasswordForm):
    pass


class ResetPasswordKeyForm(StyledFieldsMixin, forms.ResetPasswordKeyForm):
    pass


class ProfileForm(django_forms.ModelForm):
    first_name = django_forms.CharField(label=gettext_lazy('Prénom'), max_length=150, required=False)
    last_name = django_forms.CharField(label=gettext_lazy('Nom'), max_length=150, required=False)

    class Meta:
        model = Profile
        fields = ('first_name', 'last_name', 'bio', 'avatar')
        widgets = {'bio': django_forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].initial = self.instance.user.first_name
        self.fields['last_name'].initial = self.instance.user.last_name
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASS
            if name in ('first_name', 'last_name'):
                field.widget.attrs['autocomplete'] = 'given-name' if name == 'first_name' else 'family-name'
        self.fields['avatar'].widget.attrs['accept'] = 'image/jpeg,image/png,image/webp'
        self.fields['avatar'].help_text = gettext_lazy('JPG, PNG ou WebP. Sans limite de poids. Dimensions jusqu’à 4096 × 4096 pixels.')
        self.fields['bio'].help_text = gettext_lazy('Quelques mots sur vous. 500 caractères maximum.')

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if not isinstance(avatar, UploadedFile):
            return avatar
        if avatar.image.format not in {'JPEG', 'PNG', 'WEBP'}:
            raise django_forms.ValidationError(gettext_lazy('Choisissez une photo JPG, PNG ou WebP.'))
        if max(avatar.image.size) > 4096:
            raise django_forms.ValidationError(gettext_lazy('La photo ne doit pas dépasser 4096 pixels de côté.'))
        avatar.seek(0)
        try:
            with Image.open(avatar) as image:
                photo = ImageOps.exif_transpose(image).convert('RGBA')
                photo.thumbnail((512, 512))
                photo.info.clear()
                output = BytesIO()
                photo.save(output, format='PNG')
        except (OSError, ValueError) as error:
            raise django_forms.ValidationError(gettext_lazy('Cette photo est illisible. Choisissez une autre image.')) from error
        return ContentFile(output.getvalue(), name='avatar.png')

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.user.first_name = self.cleaned_data['first_name']
        profile.user.last_name = self.cleaned_data['last_name']
        if commit:
            with transaction.atomic():
                profile.user.save(update_fields=['first_name', 'last_name'])
                profile.save()
                self.save_m2m()
        return profile
