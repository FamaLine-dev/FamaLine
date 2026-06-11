#!/bin/bash
from django.contrib.auth.models import User
from apps.core.models import Profile

# Hapus semua user selain superuser (jika ada)
for user in User.objects.all():
    if not user.is_superuser:
        print(f"Menghapus: {user.username}")
        user.delete()

# Cek sisa user
print("Sisa user:", User.objects.all())
