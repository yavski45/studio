import uuid

from django import forms
from django.utils.translation import gettext_lazy
from .catalog import PACKS


class PurchaseForm(forms.Form):
    submission_id = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    pack = forms.ChoiceField(label=gettext_lazy('Votre pack'), choices=[(key, offer['name']) for key, offer in PACKS.items()], initial='starter')
