import requests
import random
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache


class FonnteService:
    def __init__(self):
        self.api_key = settings.FONNTE_API_KEY
        self.base_url = settings.FONNTE_BASE_URL
        self.sender_name = getattr(settings, 'FONNTE_SENDER_NAME', 'FamaLine')
        self.headers = {
            'Authorization': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def _format_phone_number(self, phone_number):
        """Format nomor telepon ke format internasional"""
        phone = ''.join(filter(str.isdigit, phone_number))
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        return phone
    
    def can_send_otp(self, phone_number):
        """Cek rate limit untuk kirim OTP"""
        from .models import WhatsAppOTP
        
        now = timezone.now()
        fifteen_minutes_ago = now - timedelta(minutes=15)
        
        # Maksimal 3 OTP per 15 menit
        recent_otps = WhatsAppOTP.objects.filter(
            phone_number=phone_number,
            created_at__gte=fifteen_minutes_ago
        ).count()
        
        if recent_otps >= 3:
            return False, "Terlalu banyak permintaan. Coba lagi setelah 15 menit."
        
        # Jeda 60 detik antar pengiriman
        last_otp = WhatsAppOTP.objects.filter(
            phone_number=phone_number
        ).order_by('-created_at').first()
        
        if last_otp:
            seconds_since_last = (now - last_otp.created_at).total_seconds()
            if seconds_since_last < 60:
                wait_seconds = int(60 - seconds_since_last)
                return False, f"Tunggu {wait_seconds} detik sebelum meminta kode baru."
        
        return True, "OK"
    
    def generate_and_save_otp(self, phone_number):
        """Generate OTP dan simpan ke database"""
        from .models import WhatsAppOTP
        
        can_send, message = self.can_send_otp(phone_number)
        if not can_send:
            return {'success': False, 'error': message}
        
        otp_code = f"{random.randint(100000, 999999)}"
        
        whatsapp_otp = WhatsAppOTP.objects.create(
            phone_number=phone_number,
            otp_code=otp_code,
            expires_at=timezone.now() + timedelta(minutes=5)
        )
        
        return {
            'success': True,
            'otp_id': whatsapp_otp.id,
            'otp_code': otp_code
        }
    
    def send_message(self, phone_number, message):
        """Kirim pesan teks ke WhatsApp"""
        phone_number = self._format_phone_number(phone_number)
        
        data = {
            'target': phone_number,
            'message': message,
            'countryCode': '62',
            'type': 'text',
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/send",
                headers=self.headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                return {'success': True, 'data': response.json()}
            else:
                return {'success': False, 'error': response.text}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def send_otp(self, phone_number):
        """Kirim OTP ke nomor WhatsApp"""
        phone_number = self._format_phone_number(phone_number)
        
        result = self.generate_and_save_otp(phone_number)
        if not result['success']:
            return result
        
        message = f"""*{self.sender_name} - Kode Verifikasi*

Kode verifikasi Anda adalah:

*{result['otp_code']}*

Kode ini berlaku selama 5 menit.
Jangan berikan kode ini kepada siapapun.

Tim {self.sender_name}
"""
        send_result = self.send_message(phone_number, message)
        
        if send_result['success']:
            return {'success': True, 'message': 'OTP terkirim'}
        else:
            return {'success': False, 'error': send_result['error']}
    
    def verify_otp(self, phone_number, otp_code):
        """Verifikasi OTP"""
        from .models import WhatsAppOTP
        
        phone_number = self._format_phone_number(phone_number)
        now = timezone.now()
        
        try:
            otp_record = WhatsAppOTP.objects.filter(
                phone_number=phone_number,
                is_used=False,
                expires_at__gt=now
            ).order_by('-created_at').first()
            
            if not otp_record:
                return False, "Kode OTP tidak valid atau sudah kadaluarsa."
            
            otp_record.attempt_count += 1
            otp_record.last_attempt_at = now
            otp_record.save()
            
            if otp_record.attempt_count > 5:
                otp_record.is_used = True
                otp_record.save()
                return False, "Terlalu banyak percobaan. Silakan minta kode baru."
            
            if otp_record.otp_code == otp_code:
                otp_record.is_used = True
                otp_record.save()
                return True, "Verifikasi berhasil"
            else:
                remaining = 5 - otp_record.attempt_count
                return False, f"Kode OTP salah. Sisa {remaining} percobaan."
                
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def send_template_taaruf(self, phone_number, name):
        """Kirim template pesan ta'aruf"""
        message = f"""*Assalamu'alaikum {name},*

Terima kasih telah mendaftar di Program Ta'aruf {self.sender_name}.

✅ Pendaftaran Anda telah kami terima.
📋 Tim mediator kami akan menghubungi Anda dalam 1x24 jam.

Jazakallah khair,
*Tim {self.sender_name} Ta'aruf* 🤝
"""
        return self.send_message(phone_number, message)
    
    def send_template_konsultasi(self, phone_number, name, psychologist, date, time, method):
        """Kirim template pesan konsultasi"""
        method_names = {
            'video': 'Video Call',
            'chat': 'Chat Konsultasi',
            'telepon': 'Telepon'
        }
        
        message = f"""*{self.sender_name} - Konsultasi*

Halo {name},

Booking konsultasi Anda telah kami terima!

📋 *Detail Konsultasi:*
👨‍⚕️ Psikolog: {psychologist}
📅 Tanggal: {date}
⏰ Waktu: {time}
💬 Metode: {method_names.get(method, method)}

Terima kasih,
*Tim {self.sender_name}* 🌿
"""
        return self.send_message(phone_number, message)
    
    def send_payment_success(self, phone_number, name, kelas_nama, order_id):
        """Kirim template pesan sukses pembayaran"""
        message = f"""*{self.sender_name} - Pembayaran Berhasil*

✅ Halo {name},

Pembayaran Anda untuk kelas *{kelas_nama}* telah kami terima!

🎉 Selamat! Anda sekarang memiliki akses penuh ke kelas.

🆔 Order ID: {order_id}

Silakan login ke akun Anda dan buka menu "Kelas Saya" untuk mulai belajar.

Terima kasih,
*{self.sender_name}* 🎓
"""
        return self.send_message(phone_number, message)
    
    def send_template_checkout(self, phone_number, name, kelas_nama, order_id, harga, payment_url):
        """Kirim template pesan checkout"""
        message = f"""*{self.sender_name} - Konfirmasi Order*

Halo {name},

Terima kasih telah melakukan pemesanan kelas!

📚 *Detail Kelas:*
🎓 Kelas: {kelas_nama}
💰 Harga: Rp{harga:,.0f}
🆔 Order ID: {order_id}

💳 *Link Pembayaran:*
{payment_url}

Terima kasih,
*{self.sender_name}* 🌿
"""
        return self.send_message(phone_number, message)


# Instance global
wa_service = FonnteService()


def send_whatsapp_notification(phone_number, name, notification_type, **kwargs):
    """
    Fungsi helper untuk mengirim notifikasi WhatsApp
    
    Args:
        phone_number: Nomor WhatsApp penerima
        name: Nama penerima
        notification_type: Jenis notifikasi ('otp', 'taaruf', 'konsultasi', 'checkout', 'payment_success')
        **kwargs: Parameter tambahan sesuai jenis notifikasi
    
    Returns:
        dict: {'success': bool, 'message': str, 'error': str}
    """
    if notification_type == 'otp':
        return wa_service.send_otp(phone_number)
    
    elif notification_type == 'taaruf':
        return wa_service.send_template_taaruf(phone_number, name)
    
    elif notification_type == 'konsultasi':
        return wa_service.send_template_konsultasi(
            phone_number, 
            name,
            kwargs.get('psychologist', ''),
            kwargs.get('date', ''),
            kwargs.get('time', ''),
            kwargs.get('method', '')
        )
    
    elif notification_type == 'checkout':
        return wa_service.send_template_checkout(
            phone_number,
            name,
            kwargs.get('kelas_nama', ''),
            kwargs.get('order_id', ''),
            kwargs.get('harga', 0),
            kwargs.get('payment_url', '')
        )
    
    elif notification_type == 'payment_success':
        return wa_service.send_payment_success(
            phone_number,
            name,
            kwargs.get('kelas_nama', ''),
            kwargs.get('order_id', '')
        )
    
    return {'success': False, 'error': f'Unknown notification type: {notification_type}'}


def send_otp_code(phone_number, otp_code):
    """Kirim kode OTP ke WhatsApp (untuk kompatibilitas)"""
    return wa_service.send_otp(phone_number)


def send_bulk_whatsapp(phone_numbers, message):
    """Kirim pesan ke banyak nomor"""
    results = []
    for phone in phone_numbers:
        result = wa_service.send_message(phone, message)
        results.append(result)
    return results
