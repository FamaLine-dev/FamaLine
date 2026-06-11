"""
URL configuration for famaline project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('apps.core.urls')),
    path('auth/', include('apps.accounts.urls')),  # Semua auth termasuk WhatsApp ada di sini
    path('konsultasi/', include('apps.konsultasi.urls')),
    path('social-auth/', include('social_django.urls', namespace='social')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)	

