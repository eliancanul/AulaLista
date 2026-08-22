# Provisional local runtime baseline

The production MVP starts with Django 5.2, Wagtail 7.4, Python 3.13, SQLite, server-rendered Django templates, and locally served static resources. Wagtail owns editorial authoring and workflow; AulaLista owns snapshots, sessions, practice, assistance, and pseudonymous results.

Python 3.13 is temporary because the spike produced Treebeard warnings on Python 3.14. SQLite remains until a measured 30-client test demonstrates functional loss, data loss, or a failure to meet the response targets defined for robustness. The baseline can then be revisited with evidence.
