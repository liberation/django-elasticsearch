#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "test_project.settings")

    # hack to use current django_elasticsearch package
    sys.path.insert(0, '../')

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
