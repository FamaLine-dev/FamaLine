from django.urls import path
from apps.core import views

app_name = 'konsultasi'

urlpatterns = [
    path('', views.konsultasi, name='konsultasi'),
]
