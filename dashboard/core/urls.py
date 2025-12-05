"""
Core app URL configuration.
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', views.stats_api, name='stats_api'),
    path('health/', views.health_check, name='health_check'),
]
