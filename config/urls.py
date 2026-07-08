"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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
import re

from django.contrib import admin
from django.contrib.staticfiles.views import serve as serve_static
from django.urls import include, path, re_path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

# Servis explicitement, indépendamment de DEBUG : l'application de bureau
# (voir app_desktop.py) sert le WSGI directement, sans le confort habituel
# de "runserver" pour les fichiers statiques de l'admin Django. La fonction
# standard staticfiles_urlpatterns()/static() de Django ne fait rien tant
# que DEBUG=False (volontairement désactivé ici, voir settings.py) — on
# construit donc le pattern nous-mêmes plutôt que de dépendre d'elle.
from django.conf import settings

urlpatterns += [
    re_path(
        r"^%s(?P<path>.*)$" % re.escape(settings.STATIC_URL.lstrip("/")),
        serve_static, kwargs={"insecure": True},
    ),
]
