# apps/core/forms.py
from django import forms
from .models import Artikel

class ArtikelForm(forms.ModelForm):
    class Meta:
        model = Artikel
        fields = ['judul', 'kategori', 'konten', 'penulis']
        widgets = {
            'judul': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-cream-300'}),
            'kategori': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-cream-300'}),
            'konten': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-cream-300', 'rows': 10}),
            'penulis': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-cream-300'}),
        }
