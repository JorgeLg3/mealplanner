from django.contrib.auth.decorators import login_not_required
from django.db import connection
from django.http import JsonResponse


@login_not_required  # probes and monitors aren't logged in
def health_check(_request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unhealthy"}, status=503)

    return JsonResponse({"status": "ok"})
