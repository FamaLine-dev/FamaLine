# apps/accounts/views.py

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone
from apps.core.wa_service import wa_service
from apps.core.models import Profile, WhatsAppOTP
from django.core.cache import cache
from django.contrib.auth.backends import ModelBackend
from django.core.mail import send_mail
from django.contrib.auth import update_session_auth_hash
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import json
import re
import time
import logging
import hashlib
import hmac
# Import rate limit (yang sudah dibuat)
from apps.core.rate_limit_global import global_rate_limit
from apps.core.rate_limit_per_endpoint import rate_limit

logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def generate_device_fingerprint(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    ip_address = get_client_ip(request)
    fingerprint_data = f"{user_agent}|{accept_language}|{ip_address}"
    fingerprint = hmac.new(
        settings.SECRET_KEY.encode(),
        fingerprint_data.encode(),
        hashlib.sha256
    ).hexdigest()
    return fingerprint


@csrf_protect
def forgot_password_request(request):
    """Request reset password - kirim email ke pengguna"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, 'Email wajib diisi')
            return render(request, 'accounts/forgot_password.html')
        
        # Cari user berdasarkan email
        users = User.objects.filter(email=email)
        
        if users.exists():
            user = users.first()
            
            # Generate token dan uid
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            # Buat link reset password
            reset_link = request.build_absolute_uri(
                f'/auth/reset-password/{uid}/{token}/'
            )
            
            # Kirim email
            subject = 'Reset Password FamaLine'
            message = f"""
            Halo {user.username},
            
            Kami menerima permintaan untuk mereset password akun FamaLine Anda.
            
            Klik link di bawah ini untuk mereset password Anda:
            {reset_link}
            
            Link ini berlaku selama 24 jam.
            
            Jika Anda tidak meminta reset password, abaikan email ini.
            
            Terima kasih,
            Tim FamaLine
            """
            
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                messages.success(request, 'Email reset password telah dikirim. Silakan cek inbox Anda.')
            except Exception as e:
                messages.error(request, f'Gagal mengirim email: {str(e)}')
        else:
            # Tetap tampilkan success untuk keamanan (agar tidak diketahui email terdaftar atau tidak)
            messages.success(request, 'Jika email terdaftar, kami akan mengirimkan link reset password.')
        
        return redirect('accounts:login')
    
    return render(request, 'accounts/forgot_password.html')



@csrf_protect
def reset_password_confirm(request, uidb64, token):
    """Konfirmasi reset password"""
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            errors = []
            if not new_password:
                errors.append('Password baru wajib diisi')
            elif len(new_password) < 6:
                errors.append('Password minimal 6 karakter')
            if new_password != confirm_password:
                errors.append('Konfirmasi password tidak cocok')
            
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                user.set_password(new_password)
                user.save()
                messages.success(request, 'Password berhasil diubah. Silakan login dengan password baru Anda.')
                return redirect('accounts:login')
        
        return render(request, 'accounts/reset_password.html', {'validlink': True})
    else:
        return render(request, 'accounts/reset_password.html', {'validlink': False})


@csrf_protect
@global_rate_limit  # Rate limit global
@rate_limit('login')  # Rate limit per endpoint
def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:index')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        # Authenticate dengan backend yang spesifik
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Set backend secara manual
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            messages.success(request, f'Selamat datang kembali, {username}!')
            next_url = request.GET.get('next', 'core:index')
            return redirect(next_url)
        else:
            messages.error(request, 'Username atau password salah.')
    
    return render(request, 'accounts/login.html')


@csrf_protect
@global_rate_limit
@rate_limit('register')
def register_view(request):
    if request.user.is_authenticated:
        return redirect('core:index')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        
        # Debug
        print(f"DEBUG - Register attempt: username={username}, email={email}")
        
        # Validasi sederhana
        errors = []
        
        if not first_name:
            errors.append('Nama lengkap wajib diisi')
        if not username:
            errors.append('Username wajib diisi')
        if not email:
            errors.append('Email wajib diisi')
        elif '@' not in email or '.' not in email:
            errors.append('Format email tidak valid')
        if not password1:
            errors.append('Password wajib diisi')
        elif len(password1) < 6:
            errors.append('Password minimal 6 karakter')
        if password1 != password2:
            errors.append('Konfirmasi password tidak cocok')
        
        # Cek username sudah ada
        if User.objects.filter(username=username).exists():
            errors.append('Username sudah digunakan')
        
        # Cek email sudah ada
        if User.objects.filter(email=email).exists():
            errors.append('Email sudah terdaftar')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            print(f"DEBUG - Register errors: {errors}")
        else:
            try:
                # Buat user baru dengan create_user (auto hash password)
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=first_name,
                    password=password1
                )
                
                # Simpan nomor WhatsApp
                if phone:
                    profile, created = Profile.objects.get_or_create(user=user)
                    profile.phone_number = phone
                    profile.save()
                
                print(f"DEBUG - User created successfully: {user.username}")
                
                # Langsung login
                login(request, user)
                messages.success(request, 'Akun berhasil dibuat! Selamat bergabung.')
                return redirect('core:index')
                
            except Exception as e:
                print(f"DEBUG - Register error: {str(e)}")
                messages.error(request, f'Terjadi kesalahan: {str(e)}')
    
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    messages.success(request, 'Anda telah logout.')
    return redirect('core:index')


@csrf_exempt
@require_http_methods(["POST"])
@global_rate_limit
@rate_limit('send_otp')
def send_wa_otp(request):
    """Kirim OTP ke WhatsApp - Step 1"""
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number', '').strip()
        
        if not phone_number:
            return JsonResponse({'success': False, 'error': 'Nomor WhatsApp wajib diisi'})
        
        if not re.match(r'^[0-9]{10,13}$', phone_number):
            return JsonResponse({'success': False, 'error': 'Format nomor tidak valid (10-13 digit)'})
        
        # Rate limiting per IP
        client_ip = get_client_ip(request)
        ip_key = f"otp_ip_{client_ip}"
        ip_count = cache.get(ip_key, 0)
        
        if ip_count >= 10:
            return JsonResponse({'success': False, 'error': 'Terlalu banyak permintaan. Coba lagi nanti.'})
        
        # Kirim OTP
        result = wa_service.send_otp(phone_number)
        
        if result['success']:
            # Simpan state di session server
            request.session['wa_phone'] = phone_number
            request.session['wa_step'] = 'awaiting_otp'
            request.session['wa_time'] = int(time.time())
            
            cache.set(ip_key, ip_count + 1, 3600)
            return JsonResponse({'success': True, 'message': 'Kode OTP telah dikirim'})
        else:
            error_msg = result.get('error', 'Gagal mengirim OTP')
            return JsonResponse({'success': False, 'error': error_msg})
            
    except Exception as e:
        logger.error(f"Send OTP error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan'})


@csrf_exempt
@require_http_methods(["POST"])
@global_rate_limit
@rate_limit('verify_otp')
def verify_wa_otp(request):
    """Verifikasi OTP - Step 2"""
    try:
        data = json.loads(request.body)
        otp_code = data.get('otp_code', '').strip()
        
        phone_number = request.session.get('wa_phone')
        step = request.session.get('wa_step')
        init_time = request.session.get('wa_time')
        
        if not phone_number:
            return JsonResponse({'success': False, 'error': 'Sesi habis. Silakan masukkan nomor lagi.'})
        
        if step != 'awaiting_otp':
            return JsonResponse({'success': False, 'error': 'Sesi tidak valid. Mulai dari awal.'})
        
        # Session timeout 10 menit
        if init_time and (int(time.time()) - init_time > 600):
            request.session.pop('wa_phone', None)
            request.session.pop('wa_step', None)
            request.session.pop('wa_time', None)
            return JsonResponse({'success': False, 'error': 'Sesi kadaluarsa. Silakan mulai dari awal.'})
        
        if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
            return JsonResponse({'success': False, 'error': 'Kode OTP harus 6 digit angka'})
        
        # Verifikasi OTP ke database
        success, message = wa_service.verify_otp(phone_number, otp_code)
        
        if not success:
            return JsonResponse({'success': False, 'error': message})
        
        # OTP valid, cek apakah user sudah punya PIN
        formatted_number = wa_service._format_phone_number(phone_number)
        short_number = formatted_number[-10:]
        username = f"wa_{short_number}"
        
        try:
            user = User.objects.get(username=username)
            profile = user.profile
            has_pin = bool(profile.security_pin)
        except (User.DoesNotExist, Profile.DoesNotExist):
            has_pin = False
            user = None
        
        if has_pin and user:
            # User sudah punya PIN, minta PIN
            request.session['wa_step'] = 'awaiting_pin'
            request.session['wa_user_id'] = user.id
            return JsonResponse({
                'success': True, 
                'requires_pin': True,
                'message': 'Verifikasi OTP berhasil. Masukkan PIN keamanan Anda.'
            })
        else:
            # User baru, minta buat PIN
            request.session['wa_step'] = 'awaiting_pin_setup'
            request.session['wa_temp_phone'] = phone_number
            request.session['wa_temp_formatted'] = formatted_number
            request.session['wa_temp_short'] = short_number
            request.session['wa_temp_username'] = username
            return JsonResponse({
                'success': True,
                'requires_pin_setup': True,
                'message': 'Verifikasi OTP berhasil. Buat PIN keamanan untuk akun Anda.'
            })
        
    except Exception as e:
        logger.error(f"Verify OTP error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan'})


@csrf_exempt
@require_http_methods(["POST"])
def resend_wa_otp(request):
    """Kirim ulang OTP"""
    try:
        phone_number = request.session.get('wa_phone')
        
        if not phone_number:
            return JsonResponse({'success': False, 'error': 'Sesi habis. Silakan masukkan nomor lagi.'})
        
        result = wa_service.send_otp(phone_number)
        
        if result['success']:
            request.session['wa_time'] = int(time.time())
            return JsonResponse({'success': True, 'message': 'Kode OTP baru telah dikirim'})
        else:
            return JsonResponse({'success': False, 'error': result.get('error', 'Gagal mengirim ulang')})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def cancel_wa_login(request):
    """Batal login - clear session"""
    request.session.pop('wa_phone', None)
    request.session.pop('wa_step', None)
    request.session.pop('wa_time', None)
    request.session.pop('wa_user_id', None)
    request.session.pop('wa_temp_phone', None)
    request.session.pop('wa_temp_formatted', None)
    request.session.pop('wa_temp_short', None)
    request.session.pop('wa_temp_username', None)
    request.session.pop('wa_pin_attempts', None)
    return JsonResponse({'success': True})


@csrf_exempt
@require_http_methods(["POST"])
def set_security_pin(request):
    """Set PIN keamanan untuk user baru (WhatsApp login)"""
    try:
        data = json.loads(request.body)
        pin = data.get('pin', '').strip()
        
        if not pin or len(pin) < 4 or len(pin) > 6 or not pin.isdigit():
            return JsonResponse({'success': False, 'error': 'PIN harus 4-6 digit angka'})
        
        # Ambil data dari session
        phone_number = request.session.get('wa_temp_phone')
        formatted_number = request.session.get('wa_temp_formatted')
        short_number = request.session.get('wa_temp_short')
        username = request.session.get('wa_temp_username')
        
        if not phone_number:
            return JsonResponse({'success': False, 'error': 'Sesi habis. Silakan mulai dari awal.'})
        
        # Buat user baru
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': f"{short_number}@wa.user",
                'first_name': '0' + formatted_number[2:],
                'last_name': ''
            }
        )
        
        if created:
            user.set_unusable_password()
            user.save()
        
        # Set PIN di profile
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.phone_number = phone_number
        profile.full_phone = formatted_number
        profile.security_pin = pin
        profile.pin_set_at = timezone.now()
        profile.save()
        
        # Langsung login user
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        
        # Clear session
        request.session.pop('wa_phone', None)
        request.session.pop('wa_step', None)
        request.session.pop('wa_time', None)
        request.session.pop('wa_temp_phone', None)
        request.session.pop('wa_temp_formatted', None)
        request.session.pop('wa_temp_short', None)
        request.session.pop('wa_temp_username', None)
        
        return JsonResponse({'success': True, 'redirect_url': '/'})
        
    except Exception as e:
        logger.error(f"Set PIN error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan'})


@csrf_exempt
@require_http_methods(["POST"])
@global_rate_limit
@rate_limit('verify_pin')
def verify_security_pin(request):
    """Verifikasi PIN keamanan saat login untuk user lama"""
    try:
        data = json.loads(request.body)
        pin = data.get('pin', '').strip()
        
        if not pin or len(pin) < 4 or len(pin) > 6 or not pin.isdigit():
            return JsonResponse({'success': False, 'error': 'PIN harus 4-6 digit angka'})
        
        user_id = request.session.get('wa_user_id')
        
        if not user_id:
            return JsonResponse({'success': False, 'error': 'Sesi habis. Silakan mulai dari awal.'})
        
        try:
            user = User.objects.get(id=user_id)
            profile = user.profile
        except (User.DoesNotExist, Profile.DoesNotExist):
            return JsonResponse({'success': False, 'error': 'Akun tidak ditemukan'})
        
        # Catat percobaan PIN
        attempt_key = f"pin_attempts_{user_id}"
        attempts = cache.get(attempt_key, 0)
        
        # Verifikasi PIN
        if not profile.security_pin or profile.security_pin != pin:
            attempts += 1
            cache.set(attempt_key, attempts, 300)  # 5 menit timeout
            
            if attempts >= 3:
                request.session.flush()
                return JsonResponse({'success': False, 'error': 'Terlalu banyak percobaan gagal. Silakan mulai dari awal.'})
            
            remaining = 3 - attempts
            return JsonResponse({'success': False, 'error': f'PIN salah. Sisa {remaining} percobaan.', 'remaining_attempts': remaining})
        
        # PIN benar, reset attempts
        cache.delete(attempt_key)
        
        # Simpan device fingerprint
        fingerprint = generate_device_fingerprint(request)
        profile.device_fingerprint = fingerprint
        profile.save()
        
        # Login user
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        
        # Clear session
        request.session.pop('wa_phone', None)
        request.session.pop('wa_step', None)
        request.session.pop('wa_time', None)
        request.session.pop('wa_user_id', None)
        request.session.pop('wa_pin_attempts', None)
        
        return JsonResponse({'success': True, 'redirect_url': '/'})
        
    except Exception as e:
        logger.error(f"Verify PIN error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan'})


@csrf_exempt
@require_http_methods(["POST"])
def forgot_pin_request(request):
    """Request reset PIN - kirim OTP ke WhatsApp"""
    try:
        data = json.loads(request.body)
        phone_number = data.get('phone_number', '').strip()
        
        if not phone_number:
            return JsonResponse({'success': False, 'error': 'Nomor WhatsApp wajib diisi'})
        
        if not re.match(r'^[0-9]{10,13}$', phone_number):
            return JsonResponse({'success': False, 'error': 'Format nomor tidak valid'})
        
        # Format nomor
        formatted_number = wa_service._format_phone_number(phone_number)
        short_number = formatted_number[-10:]
        username = f"wa_{short_number}"
        
        # Cek apakah user ada
        try:
            user = User.objects.get(username=username)
            profile = user.profile
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Nomor WhatsApp tidak terdaftar'})
        
        # Kirim OTP untuk reset PIN
        result = wa_service.send_otp(phone_number)
        
        if result['success']:
            # Simpan session untuk reset PIN
            request.session['reset_pin_phone'] = phone_number
            request.session['reset_pin_step'] = 'awaiting_otp'
            request.session['reset_pin_time'] = int(time.time())
            return JsonResponse({'success': True, 'message': 'Kode verifikasi telah dikirim ke WhatsApp Anda'})
        else:
            return JsonResponse({'success': False, 'error': result.get('error', 'Gagal mengirim kode')})
            
    except Exception as e:
        logger.error(f"Forgot PIN request error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan'})


@csrf_exempt
@require_http_methods(["POST"])
def forgot_pin_verify_otp(request):
    """Verifikasi OTP untuk reset PIN"""
    try:
        data = json.loads(request.body)
        otp_code = data.get('otp_code', '').strip()
        
        phone_number = request.session.get('reset_pin_phone')
        step = request.session.get('reset_pin_step')
        init_time = request.session.get('reset_pin_time')
        
        if not phone_number:
            return JsonResponse({'success': False, 'error': 'Sesi habis. Silakan mulai dari awal.'})
        
        if step != 'awaiting_otp':
            return JsonResponse({'success': False, 'error': 'Sesi tidak valid'})
        
        if init_time and (int(time.time()) - init_time > 600):
            request.session.pop('reset_pin_phone', None)
            request.session.pop('reset_pin_step', None)
            request.session.pop('reset_pin_time', None)
            return JsonResponse({'success': False, 'error': 'Sesi kadaluarsa. Silakan mulai dari awal.'})
        
        if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
            return JsonResponse({'success': False, 'error': 'Kode OTP harus 6 digit angka'})
        
        # Verifikasi OTP
        success, message = wa_service.verify_otp(phone_number, otp_code)
        
        if not success:
            return JsonResponse({'success': False, 'error': message})
        
        # OTP valid, lanjut ke set PIN baru
        request.session['reset_pin_step'] = 'awaiting_new_pin'
        return JsonResponse({'success': True, 'message': 'Verifikasi berhasil. Silakan buat PIN baru.'})
        
    except Exception as e:
        logger.error(f"Forgot PIN verify OTP error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan'})


@csrf_exempt
@require_http_methods(["POST"])
def forgot_pin_set_new(request):
    """Set PIN baru setelah verifikasi OTP"""
    try:
        data = json.loads(request.body)
        new_pin = data.get('pin', '').strip()
        
        phone_number = request.session.get('reset_pin_phone')
        step = request.session.get('reset_pin_step')
        
        if not phone_number:
            return JsonResponse({'success': False, 'error': 'Sesi habis. Silakan mulai dari awal.'})
        
        if step != 'awaiting_new_pin':
            return JsonResponse({'success': False, 'error': 'Sesi tidak valid'})
        
        if not new_pin or len(new_pin) < 4 or len(new_pin) > 6 or not new_pin.isdigit():
            return JsonResponse({'success': False, 'error': 'PIN harus 4-6 digit angka'})
        
        # Cari user
        formatted_number = wa_service._format_phone_number(phone_number)
        short_number = formatted_number[-10:]
        username = f"wa_{short_number}"
        
        try:
            user = User.objects.get(username=username)
            profile = user.profile
            profile.security_pin = new_pin
            profile.pin_set_at = timezone.now()
            profile.save()
            
            # Clear session
            request.session.pop('reset_pin_phone', None)
            request.session.pop('reset_pin_step', None)
            request.session.pop('reset_pin_time', None)
            
            # Kirim notifikasi PIN berhasil diubah
            wa_service.send_message(phone_number, f"""*{wa_service.sender_name} - PIN Berhasil Diubah*

Halo,

PIN keamanan akun Anda telah berhasil diubah.

Jika Anda tidak melakukan perubahan ini, segera hubungi tim support kami.

Terima kasih,
*Tim {wa_service.sender_name}* 🔒""")
            
            return JsonResponse({'success': True, 'message': 'PIN berhasil diubah. Silakan login kembali.'})
            
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Akun tidak ditemukan'})
            
    except Exception as e:
        logger.error(f"Forgot PIN set new error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan'})



@login_required
def profile_view(request):
    """Halaman profil pengguna"""
    user = request.user
    profile = user.profile
    
    context = {
        'user': user,
        'profile': profile,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile(request):
    """Edit profil pengguna"""
    user = request.user
    profile = user.profile
    
    if request.method == 'POST':
        # Ambil data dari form
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        username = request.POST.get('username', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        
        errors = []
        
        # Validasi username
        if username and username != user.username:
            if User.objects.filter(username=username).exists():
                errors.append('Username sudah digunakan')
            else:
                user.username = username
        
        # Validasi email
        if email and email != user.email:
            try:
                validate_email(email)
                if User.objects.filter(email=email).exclude(id=user.id).exists():
                    errors.append('Email sudah terdaftar')
                else:
                    user.email = email
            except ValidationError:
                errors.append('Format email tidak valid')
        
        # Validasi nomor WhatsApp
        if phone_number:
            import re
            if not re.match(r'^[0-9]{10,13}$', phone_number):
                errors.append('Nomor WhatsApp harus 10-13 digit angka')
            else:
                profile.phone_number = phone_number
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Simpan perubahan
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            profile.save()
            
            messages.success(request, 'Profil berhasil diperbarui!')
            return redirect('accounts:profile')
    
    context = {
        'user': user,
        'profile': profile,
    }
    return render(request, 'accounts/edit_profile.html', context)



@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    """Ganti password pengguna"""
    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        errors = []
        
        # Cek password lama
        if not request.user.check_password(current_password):
            errors.append('Password saat ini salah')
        
        # Validasi password baru
        if not new_password:
            errors.append('Password baru wajib diisi')
        elif len(new_password) < 6:
            errors.append('Password minimal 6 karakter')
        
        if new_password != confirm_password:
            errors.append('Konfirmasi password tidak cocok')
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            request.user.set_password(new_password)
            request.user.save()
            
            # Update session agar tidak logout
            update_session_auth_hash(request, request.user)
            
            # Kirim notifikasi WhatsApp jika ada nomor
            if request.user.profile.phone_number:
                from apps.core.wa_service import wa_service
                wa_service.send_message(
                    request.user.profile.phone_number,
                    f"""*{wa_service.sender_name} - Password Diubah*

Halo {request.user.first_name or request.user.username},

Password akun Anda telah berhasil diubah.

Jika Anda tidak melakukan perubahan ini, segera hubungi tim support kami.

Terima kasih,
*Tim {wa_service.sender_name}* 🔒"""
                )
            
            messages.success(request, 'Password berhasil diubah! Silakan login kembali.')
            return redirect('accounts:login')
    
    return render(request, 'accounts/change_password.html')




@login_required
@require_http_methods(["GET", "POST"])
def change_pin(request):
    """Ganti PIN keamanan"""
    user = request.user
    profile = user.profile
    
    if request.method == 'POST':
        current_pin = request.POST.get('current_pin', '').strip()
        new_pin = request.POST.get('new_pin', '').strip()
        confirm_pin = request.POST.get('confirm_pin', '').strip()
        
        errors = []
        
        # Cek PIN lama
        if not profile.security_pin:
            errors.append('Anda belum memiliki PIN. Gunakan fitur "Buat PIN"')
        elif profile.security_pin != current_pin:
            errors.append('PIN saat ini salah')
        
        # Validasi PIN baru
        if not new_pin:
            errors.append('PIN baru wajib diisi')
        elif len(new_pin) < 4 or len(new_pin) > 6:
            errors.append('PIN harus 4-6 digit')
        elif not new_pin.isdigit():
            errors.append('PIN harus berupa angka')
        
        if new_pin != confirm_pin:
            errors.append('Konfirmasi PIN tidak cocok')
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            profile.security_pin = new_pin
            profile.save()
            
            # Kirim notifikasi WhatsApp
            if profile.phone_number:
                from apps.core.wa_service import wa_service
                wa_service.send_message(
                    profile.phone_number,
                    f"""*{wa_service.sender_name} - PIN Berhasil Diubah*

Halo {user.first_name or user.username},

PIN keamanan akun Anda telah berhasil diubah.

Jika Anda tidak melakukan perubahan ini, segera hubungi tim support kami.

Terima kasih,
*Tim {wa_service.sender_name}* 🔒"""
                )
            
            messages.success(request, 'PIN keamanan berhasil diubah!')
            return redirect('accounts:profile')
    
    context = {
        'has_pin': bool(profile.security_pin)
    }
    return render(request, 'accounts/change_pin.html', context)



@login_required
@require_http_methods(["POST"])
def delete_account(request):
    """Hapus akun pengguna (dengan konfirmasi)"""
    if request.method == 'POST':
        password = request.POST.get('password', '')
        
        if not request.user.check_password(password):
            messages.error(request, 'Password salah. Akun tidak dapat dihapus.')
            return redirect('accounts:profile')
        
        # Hapus data terkait
        user = request.user
        username = user.username
        
        # Logout dulu
        logout(request)
        
        # Hapus user
        user.delete()
        
        messages.success(request, f'Akun {username} telah dihapus. Terima kasih telah menggunakan FamaLine.')
        return redirect('core:index')
    
    return redirect('accounts:profile')
