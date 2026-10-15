"""Libellés d’interface ; les codes envoyés à Murf restent inchangés."""
from django.utils.translation import gettext_lazy
LANGUAGE_NAMES = {
    'ar_SA': gettext_lazy('Arabe'), 'bn_IN': 'Bengali', 'zh_CN': gettext_lazy('Chinois mandarin'),
    'hr_HR': gettext_lazy('Croate'), 'cs_CZ': gettext_lazy('Tchèque'), 'nl_NL': gettext_lazy('Néerlandais'),
    'en_AU': gettext_lazy('Anglais · Australie'), 'en_IN': gettext_lazy('Anglais · Inde'),
    'en_SCOTT': gettext_lazy('Anglais · Écosse'), 'en_UK': gettext_lazy('Anglais · Royaume-Uni'),
    'en_US': gettext_lazy('Anglais · États-Unis'), 'fi_FI': gettext_lazy('Finnois'),
    'fr_CA': gettext_lazy('Français · Canada'), 'fr_FR': gettext_lazy('Français · France'),
    'de_DE': gettext_lazy('Allemand'), 'el_GR': gettext_lazy('Grec'), 'gu_IN': 'Gujarati',
    'hi_IN': 'Hindi', 'hu_HU': gettext_lazy('Hongrois'), 'id_ID': gettext_lazy('Indonésien'),
    'it_IT': gettext_lazy('Italien'), 'ja_JP': gettext_lazy('Japonais'), 'kn_IN': 'Kannada',
    'ko_KR': gettext_lazy('Coréen'), 'ms_MY': gettext_lazy('Malais'), 'ml_IN': 'Malayalam',
    'mr_IN': 'Marathi', 'nb_NO': gettext_lazy('Norvégien'), 'pl_PL': gettext_lazy('Polonais'),
    'pt_BR': gettext_lazy('Portugais · Brésil'), 'pt_PT': gettext_lazy('Portugais · Portugal'),
    'pa_IN': gettext_lazy('Pendjabi'), 'ro_RO': gettext_lazy('Roumain'), 'ru_RU': gettext_lazy('Russe'),
    'sk_SK': gettext_lazy('Slovaque'), 'es_MX': gettext_lazy('Espagnol · Mexique'),
    'es_ES': gettext_lazy('Espagnol · Espagne'), 'sv_SE': gettext_lazy('Suédois'),
    'tl_PH': 'Tagalog', 'ta_IN': gettext_lazy('Tamoul'), 'te_IN': gettext_lazy('Télougou'),
    'th_TH': gettext_lazy('Thaï'), 'tr_TR': gettext_lazy('Turc'), 'vi_VN': gettext_lazy('Vietnamien'),
    'uk_UA': gettext_lazy('Ukrainien'), 'da_DK': gettext_lazy('Danois'), 'no_NO': gettext_lazy('Norvégien'),
    'bg_BG': gettext_lazy('Bulgare'), 'et_EE': gettext_lazy('Estonien'), 'he_IL': gettext_lazy('Hébreu'),
    'lv_LV': gettext_lazy('Letton'), 'lt_LT': gettext_lazy('Lituanien'), 'sr_RS': gettext_lazy('Serbe'),
    'sl_SI': gettext_lazy('Slovène'), 'sw_KE': 'Swahili · Kenya',
}


def language_name(locale, fallback=None):
    return LANGUAGE_NAMES.get(locale.replace('-', '_'), fallback or locale)


def flag_code(locale):
    region = locale.replace('-', '_').rsplit('_', 1)[-1].lower()
    if region == 'uk':
        return 'gb'
    if region == 'scott':
        return 'gb-sct'
    return region if len(region) == 2 and region.isascii() and region.isalpha() else None
