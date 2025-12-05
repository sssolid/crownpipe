"""
URL configuration for CrownPipe dashboard.
"""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.core.urls')),
    path('media/', include('dashboard.media_monitor.urls')),
    path('data/', include('dashboard.data_monitor.urls')),
    path('logs/', include('dashboard.logs.urls')),
    path('api/', include('dashboard.api.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Customize admin site
admin.site.site_header = "CrownPipe Administration"
admin.site.site_title = "CrownPipe Admin"
admin.site.index_title = "Pipeline Management"
