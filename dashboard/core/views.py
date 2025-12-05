"""
Core dashboard views.

Main dashboard homepage and system-wide statistics.
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from crownpipe.common.paths import (
    MEDIA_INBOX,
    MEDIA_PENDING_BG_REMOVAL,
    MEDIA_BG_REMOVED,
    MEDIA_BG_REMOVAL_FAILED,
    MEDIA_READY_FOR_FORMATTING,
    MEDIA_PRODUCTS,
    MEDIA_PRODUCTION,
)


def get_pipeline_stats():
    """Get statistics for all pipelines."""
    stats = {
        'media': {
            'inbox': len(list(MEDIA_INBOX.iterdir())) if MEDIA_INBOX.exists() else 0,
            'pending_bg_removal': len(list(MEDIA_PENDING_BG_REMOVAL.iterdir())) if MEDIA_PENDING_BG_REMOVAL.exists() else 0,
            'bg_removed': len(list(MEDIA_BG_REMOVED.iterdir())) if MEDIA_BG_REMOVED.exists() else 0,
            'bg_removal_failed': len(list(MEDIA_BG_REMOVAL_FAILED.iterdir())) if MEDIA_BG_REMOVAL_FAILED.exists() else 0,
            'ready_for_formatting': len(list(MEDIA_READY_FOR_FORMATTING.iterdir())) if MEDIA_READY_FOR_FORMATTING.exists() else 0,
            'total_products': len(list(MEDIA_PRODUCTS.iterdir())) if MEDIA_PRODUCTS.exists() else 0,
            'in_production': len(list(MEDIA_PRODUCTION.iterdir())) if MEDIA_PRODUCTION.exists() else 0,
        },
        'data': {
            # Data pipeline stats will be added
        }
    }
    return stats


def index(request):
    """Main dashboard homepage."""
    stats = get_pipeline_stats()
    return render(request, 'core/index.html', {
        'stats': stats,
        'page_title': 'Dashboard'
    })


@require_http_methods(["GET"])
def stats_api(request):
    """API endpoint for pipeline statistics (for HTMX auto-refresh)."""
    stats = get_pipeline_stats()
    
    if request.htmx:
        # Return partial HTML for HTMX
        return render(request, 'core/_stats_partial.html', {'stats': stats})
    
    # Return JSON for regular requests
    return JsonResponse(stats)


def health_check(request):
    """Health check endpoint."""
    from crownpipe.common.db import test_connection
    
    db_healthy = test_connection()
    
    status = {
        'status': 'healthy' if db_healthy else 'unhealthy',
        'database': 'connected' if db_healthy else 'disconnected',
    }
    
    return JsonResponse(status, status=200 if db_healthy else 503)
