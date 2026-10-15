from django.utils.translation import gettext_lazy
from django.shortcuts import render
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator
from django.utils.cache import patch_vary_headers
from allauth.account import views as account_views
from allauth.account.models import EmailAddress
from django.db import transaction
from botocore.exceptions import BotoCoreError, ClientError
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from smtplib import SMTPException
import logging

from .forms import ProfileForm
from .models import Profile
from .signals import delete_avatar_after_commit


logger = logging.getLogger(__name__)


class AuthPageMixin:
    auth_mode = 'login'

    def email_failure_response(self, form, error):
        logger.warning('Envoi email indisponible : %s', type(error).__name__)
        form.add_error(None, gettext_lazy('Le service d’email est momentanément indisponible. Réessayez plus tard.'))
        return self.form_invalid(form)

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except (SMTPException, OSError) as error:
            return self.email_failure_response(form, error)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(auth_mode=self.auth_mode, google_enabled=settings.GOOGLE_OAUTH_ENABLED)
        return context

    def get_template_names(self):
        if self.request.headers.get('HX-Request') == 'true':
            return ['comptes/_auth_card.html']
        return ['comptes/auth.html']

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        patch_vary_headers(response, ['HX-Request'])
        return response


@method_decorator(never_cache, name='dispatch')
class SignupView(AuthPageMixin, account_views.SignupView):
    auth_mode = 'signup'

    def form_valid(self, form):
        try:
            # Éviter un compte partiellement créé si un envoi obligatoire échoue.
            with transaction.atomic():
                return account_views.SignupView.form_valid(self, form)
        except (SMTPException, OSError) as error:
            return self.email_failure_response(form, error)


@method_decorator(never_cache, name='dispatch')
class LoginView(AuthPageMixin, account_views.LoginView):
    auth_mode = 'login'


@method_decorator(never_cache, name='dispatch')
class PasswordResetView(AuthPageMixin, account_views.PasswordResetView):
    auth_mode = 'reset'


@login_required
@never_cache
def espace(request):
    if not EmailAddress.objects.filter(
        user=request.user, email__iexact=request.user.email, verified=True,
    ).exists():
        return render(request, 'account/verified_email_required.html', status=403)
    return render(request, 'comptes/espace.html')


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def profile(request):
    if not EmailAddress.objects.filter(
        user=request.user, email__iexact=request.user.email, verified=True,
    ).exists():
        return render(request, 'account/verified_email_required.html', status=403)
    user_profile, _ = Profile.objects.get_or_create(user=request.user)
    old_avatar = user_profile.avatar.name
    avatar_storage = user_profile.avatar.storage
    form = ProfileForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
        instance=user_profile,
    )
    saved = False
    if request.method == 'POST' and form.is_valid():
        try:
            user_profile = form.save()
        except (BotoCoreError, ClientError, OSError) as error:
            logger.warning('Enregistrement de photo indisponible : %s', type(error).__name__)
            form.add_error('avatar', gettext_lazy('La photo n’a pas pu être enregistrée. Réessayez dans un instant.'))
        else:
            if old_avatar and old_avatar != user_profile.avatar.name:
                delete_avatar_after_commit(avatar_storage, old_avatar)
            if request.headers.get('HX-Request') != 'true':
                return redirect(reverse('profil_compte') + '?saved=1')
            saved = True
            form = ProfileForm(instance=user_profile)
    avatar_url = ''
    # En cas d’échec, afficher la photo enregistrée plutôt que le fichier non envoyé.
    if form.errors:
        user_profile.refresh_from_db()
    if user_profile.avatar:
        avatar_url = user_profile.avatar.url
    context = {'form': form, 'profile': user_profile, 'avatar_url': avatar_url,
               'saved': saved or request.GET.get('saved') == '1'}
    template = 'comptes/_profile_card.html' if request.headers.get('HX-Request') == 'true' else 'comptes/profile.html'
    response = render(request, template, context)
    patch_vary_headers(response, ['HX-Request'])
    return response
