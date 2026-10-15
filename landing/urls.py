from django.urls import path
from . import views

app_name = 'landing'

urlpatterns = [
    path('', views.home, name='home'), 
    path('fr/', views.localized_home, {'language': 'fr'}, name='localized_home'),
    path('en/', views.localized_home, {'language': 'en'}, name='localized_home'),
    
    ]
