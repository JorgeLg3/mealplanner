from django.http import JsonResponse
from django.db import connection


def health_check(_request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unhealthy"}, status=503)

    return JsonResponse({"status": "ok"})
