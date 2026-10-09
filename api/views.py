"""The retired Vue entry now returns teachers to the supported Django shell."""
from django.shortcuts import redirect
from curriculum.views import teacher_required


@teacher_required
def sprint_shell(request):
    return redirect("tutor-curriculum")
