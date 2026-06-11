#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
# MATIKAN BYTECODE SEBELUM APA PUN
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
# HAPUS __pycache__ YANG SUDAH ADA
import subprocess
subprocess.run('find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null', shell=True)

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'famaline.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
