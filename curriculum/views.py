from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from curriculum.models import ClassroomSession, PublishedPackageSnapshot


def student_packages(request):
    return render(request, "curriculum/student_packages.html", {"packages": []})


@require_POST
def start_student_session(request, snapshot_id):
    snapshot = get_object_or_404(PublishedPackageSnapshot, pk=snapshot_id)
    session = ClassroomSession.start_from_snapshot(snapshot)
    return redirect("student-activity", session_id=session.pk)


def student_activity(request, session_id):
    session = get_object_or_404(
        ClassroomSession.objects.select_related("snapshot"),
        pk=session_id,
    )
    return render(
        request,
        "curriculum/student_activity.html",
        {
            "session": session,
            "snapshot_payload": session.snapshot.payload,
        },
    )
