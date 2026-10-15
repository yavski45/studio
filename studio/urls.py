from django.urls import path
from . import views

app_name = 'studio'
urlpatterns = [
    path('', views.create, name='create'),
    path('projets/', views.index, name='index'),
    path('nouveau/', views.legacy_create, name='legacy_create'),
    path('<uuid:pk>/', views.detail, name='detail'),
    path('<uuid:pk>/statut/', views.status, name='status'),
    path('<uuid:pk>/reprendre/', views.resume, name='resume'),
    path('<uuid:pk>/original/lecture/', views.watch, name='original'),
    path('<uuid:pk>/sorties/<int:output_id>/lecture/', views.watch, name='watch'),
    path('<uuid:pk>/sorties/<int:output_id>/<str:kind>/', views.download, name='download'),
]
