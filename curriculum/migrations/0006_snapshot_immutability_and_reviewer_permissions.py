from django.db import migrations


UPDATE_TRIGGER = "curriculum_publishedpackagesnapshot_no_update"
DELETE_TRIGGER = "curriculum_publishedpackagesnapshot_no_delete"
TABLE_NAME = "curriculum_publishedpackagesnapshot"


def grant_reviewer_permissions_and_create_triggers(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    package_content_type = ContentType.objects.get(
        app_label="curriculum",
        model="curriculumpackage",
    )
    reviewer_group, _ = Group.objects.get_or_create(name="EditorialReviewer")
    for codename, name in (
        ("add_curriculumpackage", "Can add CurriculumPackage"),
        ("change_curriculumpackage", "Can change CurriculumPackage"),
        ("publish_curriculumpackage", "Can publish CurriculumPackage"),
    ):
        permission, _ = Permission.objects.get_or_create(
            content_type=package_content_type,
            codename=codename,
            defaults={"name": name},
        )
        reviewer_group.permissions.add(permission)

    if schema_editor.connection.vendor != "sqlite":
        return

    schema_editor.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS {UPDATE_TRIGGER}
        BEFORE UPDATE ON {TABLE_NAME}
        BEGIN
            SELECT RAISE(ABORT, 'PublishedPackageSnapshot is immutable');
        END;
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS {DELETE_TRIGGER}
        BEFORE DELETE ON {TABLE_NAME}
        BEGIN
            SELECT RAISE(ABORT, 'PublishedPackageSnapshot is immutable');
        END;
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0005_alter_publishedpackagesnapshot_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            grant_reviewer_permissions_and_create_triggers,
            # Keep the protection while PublishedPackageSnapshot exists;
            # SQLite removes the triggers with the table in migration 0002.
            migrations.RunPython.noop,
        ),
    ]
