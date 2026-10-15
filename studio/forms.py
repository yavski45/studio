from django.utils.translation import gettext_lazy
import uuid
from pathlib import Path

from django import forms
from django.conf import settings

from .models import DubbingLanguage
from .widgets import LanguageButtons, SourceLanguageButtons

FIELD_STYLE = 'w-full rounded-xl border border-[#2b4035] bg-[#131e19] px-4 py-3 text-sm outline-none focus:border-[#60dda5] focus:ring-2 focus:ring-[#60dda5]/15'


class DubbingForm(forms.Form):
    submission_id = forms.UUIDField(widget=forms.HiddenInput)
    title = forms.CharField(label=gettext_lazy('Nom du doublage'), max_length=120)
    video = forms.FileField(label=gettext_lazy('Votre vidéo'), widget=forms.FileInput(attrs={'accept': '.mp4,.mov,.webm,.mkv,.avi'}))
    source_locale = forms.ChoiceField(label=gettext_lazy('Langue de la vidéo'), required=False, initial='',
        widget=SourceLanguageButtons(attrs={'class': 'language-options'}))
    target_locales = forms.MultipleChoiceField(label=gettext_lazy('Langues du doublage'), widget=LanguageButtons(attrs={'class': 'language-options'}))
    consent = forms.BooleanField(label=gettext_lazy('Je dispose des droits nécessaires et j’autorise le traitement de cette vidéo par Murf pour son doublage.'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['submission_id'].initial = uuid.uuid4()
        languages = list(DubbingLanguage.objects.filter(source=True) | DubbingLanguage.objects.filter(target=True))
        self.fields['source_locale'].choices = [('', gettext_lazy('Détection automatique'))] + sorted(
            [(lang.locale, lang.display_name) for lang in languages if lang.source], key=lambda item: item[1])
        self.fields['target_locales'].choices = sorted(
            [(lang.locale, lang.display_name) for lang in languages if lang.target], key=lambda item: item[1])
        for name in ('title', 'video'):
            self.fields[name].widget.attrs['class'] = FIELD_STYLE
        self.fields['title'].widget.attrs['x-model'] = 'title'
        self.fields['consent'].widget.attrs['class'] = 'accent-[#60dda5]'

    def clean_video(self):
        video = self.cleaned_data['video']
        extension = Path(video.name).suffix.lower()
        if extension not in {'.mp4', '.mov', '.webm', '.mkv', '.avi'}:
            raise forms.ValidationError(gettext_lazy('Choisissez une vidéo MP4, MOV, WebM, MKV ou AVI.'))
        if not video.size:
            raise forms.ValidationError(gettext_lazy('Le fichier est vide.'))
        limit = settings.STUDIO_MAX_UPLOAD_BYTES
        if limit and video.size > limit:
            raise forms.ValidationError(gettext_lazy('La vidéo dépasse la limite de %(limit)s Mo.') % {'limit': limit // (1024 ** 2)})
        header = video.read(32)
        video.seek(0)
        valid = (extension in {'.mp4', '.mov'} and header[4:8] in {b'ftyp', b'moov', b'mdat', b'wide'}) or (extension in {'.webm', '.mkv'} and header.startswith(b'\x1aE\xdf\xa3')) or (extension == '.avi' and header.startswith(b'RIFF') and header[8:12] == b'AVI ')
        if not valid:
            raise forms.ValidationError(gettext_lazy('Le contenu du fichier ne correspond pas à un format vidéo accepté.'))
        return video

    def clean(self):
        data = super().clean()
        if data.get('source_locale') in data.get('target_locales', []):
            self.add_error('target_locales', gettext_lazy('Choisissez une langue différente de celle de la vidéo.'))
        return data

    def clean_target_locales(self):
        return list(dict.fromkeys(self.cleaned_data['target_locales']))
