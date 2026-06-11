from django.contrib import admin
from .models import Artikel, PendaftaranTaaruf, Subscriber, BookingKonsultasi

@admin.register(Artikel)
class ArtikelAdmin(admin.ModelAdmin):
    list_display = ['judul', 'kategori', 'penulis', 'created_at', 'dibaca']
    list_filter = ['kategori', 'created_at']
    search_fields = ['judul', 'konten']
    prepopulated_fields = {'slug': ('judul',)}

@admin.register(PendaftaranTaaruf)
class PendaftaranTaarufAdmin(admin.ModelAdmin):
    list_display = ['nama_lengkap', 'jenis_kelamin', 'email', 'whatsapp', 'status', 'wa_notification_sent', 'created_at']
    list_filter = ['jenis_kelamin', 'status', 'wa_notification_sent', 'created_at']
    search_fields = ['nama_lengkap', 'email', 'whatsapp']
    list_editable = ['status']

@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ['email', 'created_at']
    search_fields = ['email']

@admin.register(BookingKonsultasi)
class BookingKonsultasiAdmin(admin.ModelAdmin):
    list_display = ['nama', 'psikolog', 'tanggal', 'waktu', 'metode', 'status', 'wa_notification_sent', 'created_at']
    list_filter = ['psikolog', 'metode', 'status', 'wa_notification_sent']
    search_fields = ['nama', 'email', 'whatsapp']
    list_editable = ['status']
