"""
URL configuration for dublao project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog
from django.conf import settings
from . import errors
from . import seo

handler400 = 'dublao.errors.bad_request'
handler403 = 'dublao.errors.permission_denied'
handler404 = 'dublao.errors.page_not_found'
handler500 = 'dublao.errors.server_error'

urlpatterns = [
    path('robots.txt', seo.robots, name='robots'),
    path('sitemap.xml', seo.sitemap, name='sitemap'),
    path('i18n/', include('django.conf.urls.i18n')),
    path('i18n/javascript/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    path('administration/', include('supervision.urls')),
    path('credits/', include('credits.urls')),
    path('studio/', include('studio.urls')),
    path('', include('landing.urls')),
    path('comptes/', include('comptes.urls')),
    path('comptes/', include('allauth.urls')),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += [path('erreurs/<int:code>/', errors.preview, name='error-preview')]
