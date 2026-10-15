from django.shortcuts import render
from credits.catalog import PACKS
from studio.models import DubbingLanguage
from .demos import DEMO_VIDEOS
from django.utils.translation import get_language, override
from dublao.seo import homepage_metadata




def home(request): 
    languages = list(DubbingLanguage.objects.filter(target=True))
    return render(request, 'landing/home.html', {
        'credit_packs': [{'key': key, **pack} for key, pack in PACKS.items()],
        'target_language_count': len(languages), 'target_languages': languages,
        'demo_videos': DEMO_VIDEOS,
        'seo': homepage_metadata(get_language(), len(languages)),
        'language_next_url': '/',
    })


def localized_home(request, language):
    with override(language):
        response = home(request)
        response['Content-Language'] = language
        return response

