from django.shortcuts import render


def student_packages(request):
    return render(request, "curriculum/student_packages.html", {"packages": []})
