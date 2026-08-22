from django.shortcuts import render


def health_page(request):
    return render(request, "health/health.html", {"health_status": "healthy"})
