from django.db import migrations


WORKFLOW_NAME = "EditorialReviewer approval"
TASK_NAME = "EditorialReviewer approval"
GROUP_NAME = "EditorialReviewer"


def create_editorial_review_workflow(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Workflow = apps.get_model("wagtailcore", "Workflow")
    WorkflowContentType = apps.get_model("wagtailcore", "WorkflowContentType")
    WorkflowTask = apps.get_model("wagtailcore", "WorkflowTask")
    GroupApprovalTask = apps.get_model("wagtailcore", "GroupApprovalTask")

    reviewer_group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    package_content_type, _ = ContentType.objects.get_or_create(
        app_label="curriculum",
        model="curriculumpackage",
    )
    task_content_type, _ = ContentType.objects.get_or_create(
        app_label="wagtailcore",
        model="groupapprovaltask",
    )
    task, _ = GroupApprovalTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={"content_type": task_content_type},
    )
    task.active = True
    task.content_type = task_content_type
    task.save()
    task.groups.set([reviewer_group])

    workflow, _ = Workflow.objects.get_or_create(
        name=WORKFLOW_NAME,
        defaults={"active": True},
    )
    workflow.active = True
    workflow.save()
    WorkflowTask.objects.update_or_create(
        workflow=workflow,
        task=task,
        defaults={"sort_order": 0},
    )
    WorkflowContentType.objects.update_or_create(
        content_type=package_content_type,
        defaults={"workflow": workflow},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0003_curriculumpackage_expire_at_and_more"),
    ]

    operations = [
        migrations.RunPython(
            create_editorial_review_workflow,
            # The named group, task, and workflow may be shared or preexisting;
            # reversing this migration must never remove editorial authority.
            migrations.RunPython.noop,
        ),
    ]
