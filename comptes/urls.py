from django.urls import path
from django.views.generic.base import RedirectView
from . import views

# Garder les noms publics allauth pour ses liens et ses emails.
urlpatterns = [
    path('signup/', views.SignupView.as_view(), name='account_signup'),
    path('login/', views.LoginView.as_view(), name='account_login'),
    path('password/reset/', views.PasswordResetView.as_view(), name='account_reset_password'),
    path('email/', RedirectView.as_view(pattern_name='espace_compte'), name='account_email'),
    path('espace/', views.espace, name='espace_compte'),
    path('profil/', views.profile, name='profil_compte'),
]
