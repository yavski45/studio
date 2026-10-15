"""Public prerecorded examples supplied by the product owner."""
from django.utils.translation import gettext_lazy
DEMO_VIDEOS = (
    {'locale': 'ko_KR', 'name': gettext_lazy('Coréen'), 'flag': 'kr', 'lang': 'ko'},
    {'locale': 'ru_RU', 'name': gettext_lazy('Russe'), 'flag': 'ru', 'lang': 'ru'},
    {'locale': 'ar_SA', 'name': gettext_lazy('Arabe'), 'flag': 'sa', 'lang': 'ar'},
)
