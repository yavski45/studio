from django.urls import path
from . import views

app_name = 'supervision'
urlpatterns = [path('', views.dashboard, name='dashboard'),
    path('alertes/murf/', views.murf_alert, name='murf-alert'),
    path('alertes/murf/actualiser/', views.refresh_murf, name='murf-refresh')]
