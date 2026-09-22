from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """Simple health check endpoint for Docker and load balancers."""
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"

    status = 200 if db_status == "ok" else 503
    return JsonResponse({
        "status": "ok" if status == 200 else "error",
        "database": db_status,
    }, status=status)
