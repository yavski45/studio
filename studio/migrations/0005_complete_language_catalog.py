from django.db import migrations


# Catalogue des 44 langues AUTOMATED confirmé avec l'API Murf le 14/10/2026.
# Les huit langues indiquées ici ne sont pas des langues sources du compte.
TARGETS = [
    ('ar_SA', 'Arabic'), ('bn_IN', 'Bengali'), ('cs_CZ', 'Czech'),
    ('de_DE', 'German'), ('el_GR', 'Greek'), ('en_AU', 'English - Australia'),
    ('en_IN', 'English - India'), ('en_SCOTT', 'English - Scottish'),
    ('en_UK', 'English - UK'), ('en_US', 'English - US'),
    ('es_ES', 'Spanish - Spain'), ('es_MX', 'Spanish - Mexico'),
    ('fi_FI', 'Finnish'), ('fr_CA', 'French - Canada'), ('fr_FR', 'French - France'),
    ('gu_IN', 'Gujarati'), ('hi_IN', 'Hindi'), ('hr_HR', 'Croatian'),
    ('hu_HU', 'Hungarian'), ('id_ID', 'Indonesian'), ('it_IT', 'Italian'),
    ('ja_JP', 'Japanese'), ('kn_IN', 'Kannada'), ('ko_KR', 'Korean'),
    ('ml_IN', 'Malayalam'), ('mr_IN', 'Marathi'), ('ms_MY', 'Malay'),
    ('nb_NO', 'Norwegian'), ('nl_NL', 'Dutch'), ('pa_IN', 'Punjabi'),
    ('pl_PL', 'Polish'), ('pt_BR', 'Portuguese - Brazil'), ('pt_PT', 'Portuguese - Portugal'),
    ('ro_RO', 'Romanian'), ('ru_RU', 'Russian'), ('sk_SK', 'Slovak'),
    ('sv_SE', 'Swedish'), ('ta_IN', 'Tamil'), ('te_IN', 'Telugu'),
    ('th_TH', 'Thai'), ('tl_PH', 'Tagalog'), ('tr_TR', 'Turkish'),
    ('vi_VN', 'Vietnamese'), ('zh_CN', 'Chinese - Mandarin'),
]
TARGET_ONLY = {'gu_IN', 'kn_IN', 'ml_IN', 'mr_IN', 'ms_MY', 'nb_NO', 'pa_IN', 'tl_PH'}


def complete_catalog(apps, schema_editor):
    language = apps.get_model('studio', 'DubbingLanguage')
    for locale, name in TARGETS:
        # Ne pas remplacer les choix d'un catalogue déjà synchronisé.
        language.objects.using(schema_editor.connection.alias).get_or_create(
            locale=locale, defaults={'name': name, 'target': True, 'source': locale not in TARGET_ONLY})


class Migration(migrations.Migration):
    dependencies = [('studio', '0004_dubbingjob_murf_rejected_job_ids_and_more')]
    operations = [migrations.RunPython(complete_catalog, migrations.RunPython.noop)]
