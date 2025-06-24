"""
URL configuration for NashCRM project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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
from django.urls import path, include

from backend import views
from backend.views import leads_report_page, map_search_view
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.home, name="home"),
    path("admin/report/leads/", admin.site.admin_view(leads_report_page), name="admin_leads_report"),
    path("admin/map-search/", map_search_view, name="map_search"),

    path('admin/', admin.site.urls),
    path('api/', include('backend.urls')),  # ← сюди летить весь API з backend/
    path('whatsapp/', include('whatsapp.urls')),


] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
