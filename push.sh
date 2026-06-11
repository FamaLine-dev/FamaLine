#!/bin/bash

# Target repositori GitHub
REPO_URL="https://github.com/FamaLine-dev/FamaLine.git"

# 1. Pastikan folder ini adalah repositori Git
if [ ! -d ".git" ]; then
    echo "⚠️  Folder ini belum di-inisialisasi sebagai Git repository."
    echo "Menginisialisasi Git..."
    git init
    git add .
fi

# 2. Atur atau perbarui Remote URL
CURRENT_REMOTE=$(git remote get-url origin 2>/dev/null)

if [ -z "$CURRENT_REMOTE" ]; then
    echo "🌐 Menambahkan remote origin ke: $REPO_URL"
    git remote add origin "$REPO_URL"
elif [ "$CURRENT_REMOTE" != "$REPO_URL" ]; then
    echo "🔄 Memperbarui remote origin ke: $REPO_URL"
    git remote set-url origin "$REPO_URL"
fi

# 3. Minta input pesan commit dari user
echo "💬 Masukkan pesan commit (tekan Enter untuk default 'Update'):"
read -r commit_message

if [ -z "$commit_message" ]; then
    commit_message="Update $(date +'%Y-%m-%d %H:%M:%S')"
fi

# 4. Amankan nama branch agar tetap 'main' (Menghindari 'master')
BRANCH=$(git branch --show-current)

# Jika repository baru (belum ada branch) atau branch aktif saat ini bernama 'master'
if [ -z "$BRANCH" ] || [ "$BRANCH" = "master" ]; then
    BRANCH="main"
    git branch -M main
fi

# 5. Proses Git Stage, Commit, dan Push
echo "🚀 Memulai proses push ke branch '$BRANCH'..."

git add .

if git commit -m "$commit_message"; then
    # Push ke upstream origin
    git push -u -f origin "$BRANCH"
    
    if [ $? -eq 0 ]; then
        echo "✅ Berhasil push ke $REPO_URL ($BRANCH)"
    else
        echo "❌ Gagal melakukan push. Periksa koneksi atau hak akses token/SSH Anda."
    fi
else
    echo "ℹ️  Tidak ada perubahan yang perlu di-commit."
fi
