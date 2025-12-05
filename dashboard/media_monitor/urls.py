"""Media monitor app URLs."""
from django.urls import path
from django.views.generic import TemplateView

app_name = 'media_monitor'

urlpatterns = [
    path('', TemplateView.as_view(template_name='media_monitor/index.html'), name='index'),
]
