"""Logs app URLs."""
from django.urls import path
from django.views.generic import TemplateView

app_name = 'logs'

urlpatterns = [
    path('', TemplateView.as_view(template_name='logs/index.html'), name='index'),
]
