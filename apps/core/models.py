from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


class Artikel(models.Model):
    CATEGORY_CHOICES = [
        ('balita', 'Balita & Anak'),
        ('psikologi', 'Psikologi Anak'),
        ('remaja', 'Remaja & Digital'),
        ('keluarga', 'Keluarga Sakinah'),
    ]
    
    judul = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    kategori = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    konten = models.TextField()
    gambar = models.ImageField(upload_to='artikel/', blank=True, null=True)
    penulis = models.CharField(max_length=100, default='FamaLine')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    dibaca = models.IntegerField(default=0)
    
    def __str__(self):
        return self.judul


class PendaftaranTaaruf(models.Model):
    JENIS_KELAMIN = [
        ('Pria', 'Pria'),
        ('Wanita', 'Wanita'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Menunggu'),
        ('contacted', 'Sudah Dihubungi'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
    ]
    
    nama_lengkap = models.CharField(max_length=100)
    jenis_kelamin = models.CharField(max_length=10, choices=JENIS_KELAMIN)
    tanggal_lahir = models.DateField(null=True, blank=True)
    domisili = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    whatsapp = models.CharField(max_length=15)
    pekerjaan = models.CharField(max_length=100, blank=True)
    pendidikan = models.CharField(max_length=50, blank=True)
    kriteria_pasangan = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    wa_notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.nama_lengkap} - {self.created_at.date()}"


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.email


class BookingKonsultasi(models.Model):
    METODE_CHOICES = [
        ('video', 'Video Call - Rp175.000'),
        ('chat', 'Chat Konsultasi - Rp125.000'),
        ('telepon', 'Telepon - Rp150.000'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Menunggu'),
        ('confirmed', 'Terkonfirmasi'),
        ('completed', 'Selesai'),
        ('cancelled', 'Dibatalkan'),
    ]
    
    nama = models.CharField(max_length=100)
    email = models.EmailField()
    whatsapp = models.CharField(max_length=15)
    psikolog = models.CharField(max_length=100)
    tanggal = models.DateField()
    waktu = models.CharField(max_length=10)
    topik = models.TextField()
    metode = models.CharField(max_length=20, choices=METODE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    wa_notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.nama} - {self.tanggal} {self.waktu}"


class KelasOrder(models.Model):
    PAYMENT_STATUS = [
        ('pending', 'Menunggu Pembayaran'),
        ('processing', 'Diproses'),
        ('paid', 'Lunas'),
        ('expired', 'Kadaluarsa'),
        ('cancelled', 'Dibatalkan'),
        ('failed', 'Gagal'),
    ]
    
    PAYMENT_METHOD = [
        ('credit_card', 'Kartu Kredit'),
        ('bank_transfer', 'Transfer Bank'),
        ('qris', 'QRIS'),
        ('midtrans', 'Midtrans'),
    ]
    
    GATEWAY_CHOICES = [
        ('midtrans', 'Midtrans'),
        ('xendit', 'Xendit'),
        ('tripay', 'Tripay'),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='kelas_orders'
    )
    order_id = models.CharField(max_length=50, unique=True)
    kelas_id = models.IntegerField()
    kelas_nama = models.CharField(max_length=200)
    kelas_harga = models.IntegerField()
    nama = models.CharField(max_length=100)
    email = models.EmailField()
    whatsapp = models.CharField(max_length=15)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD, default='midtrans')
    payment_gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default='midtrans')
    payment_token = models.CharField(max_length=255, blank=True, null=True)
    payment_url = models.TextField(blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.order_id} - {self.kelas_nama} - {self.status}"


class UserKelasAccess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kelas_access')
    kelas_id = models.IntegerField()
    kelas_nama = models.CharField(max_length=200)
    order_id = models.CharField(max_length=50)
    access_granted = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('user', 'kelas_id')
    
    def __str__(self):
        return f"{self.user.username} - {self.kelas_nama}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    full_phone = models.CharField(max_length=15, blank=True, null=True)
    security_pin = models.CharField(max_length=6, blank=True, null=True)
    pin_set_at = models.DateTimeField(null=True, blank=True)
    device_fingerprint = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.phone_number or 'No phone'}"


class WhatsAppOTP(models.Model):
    """Model untuk menyimpan OTP WhatsApp di server"""
    phone_number = models.CharField(max_length=15, db_index=True)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempt_count = models.IntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['phone_number', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.phone_number} - {self.otp_code}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        Profile.objects.create(user=instance)
    instance.profile.save()



# Tambahkan di apps/core/models.py

class ChatbotFAQ(models.Model):
    """Model untuk menyimpan FAQ chatbot"""
    CATEGORY_CHOICES = [
        ('kelas', 'Kelas Online'),
        ('konsultasi', 'Konsultasi'),
        ('taaruf', 'Ta\'aruf'),
        ('artikel', 'Artikel'),
        ('harga', 'Harga & Promo'),
        ('akun', 'Akun & Login'),
        ('umum', 'Umum'),
    ]
    
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='umum')
    keywords = models.TextField(help_text='Kata kunci dipisah koma (contoh: kelas, kursus, belajar)')
    question = models.CharField(max_length=255)
    answer = models.TextField()
    button_text = models.CharField(max_length=50, blank=True, null=True, help_text='Teks tombol (opsional)')
    button_icon = models.CharField(max_length=10, blank=True, null=True, help_text='Emoji icon (contoh: 📚)')
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = 'FAQ Chatbot'
        verbose_name_plural = 'FAQ Chatbot'
    
    def get_keywords_list(self):
        return [k.strip().lower() for k in self.keywords.split(',') if k.strip()]
    
    def __str__(self):
        return f"{self.get_category_display()} - {self.question[:50]}"


class ChatbotConversation(models.Model):
    """Model untuk menyimpan history percakapan (opsional)"""
    session_id = models.CharField(max_length=100, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    message = models.TextField()
    response = models.TextField()
    intent = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.session_id} - {self.created_at}"
