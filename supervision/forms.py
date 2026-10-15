from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy


class ReportForm(forms.Form):
    period = forms.ChoiceField(choices=[('7', gettext_lazy('7 jours')), ('30', gettext_lazy('30 jours')), ('90', gettext_lazy('90 jours'))], initial='30')
    currency = forms.ChoiceField(choices=[('USD', gettext_lazy('Dollars · USD')), ('XOF', gettext_lazy('FCFA · XOF'))], initial='USD')
    rate = forms.DecimalField(required=False, min_value=Decimal('0.000001'),
                              max_value=Decimal('100000'), max_digits=12, decimal_places=6)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('currency') == 'XOF' and not cleaned.get('rate'):
            self.add_error('rate', gettext_lazy('Renseignez le taux de conversion : nombre de FCFA pour 1 dollar.'))
        return cleaned
