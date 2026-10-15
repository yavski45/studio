from django.urls import path
from . import views



app_name = 'credits'
urlpatterns = [
    path('', views.wallet, name='wallet'),
    path('acheter/', views.buy, name='buy'),
    path('callback/', views.payment_callback, name='callback'),
    path('retour/<uuid:pk>/', views.payment_return, name='return'),
    path('achats/<uuid:pk>/', views.purchase, name='purchase'),
    path('achats/<uuid:pk>/verifier/', views.verify, name='verify'),
    path('webhook/geniuspay/', views.webhook, name='webhook'),
]
