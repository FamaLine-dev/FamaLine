from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils.text import slugify  # ← TAMBAHKAN INI
from django.views.decorators.http import require_http_methods

from datetime import timedelta
import uuid
import json
import requests

from datetime import datetime
from .models import Artikel, PendaftaranTaaruf, Subscriber, BookingKonsultasi, KelasOrder
from .midtrans_payment import midtrans_payment, get_midtrans_status
from .wa_service import wa_service, send_whatsapp_notification

from django.contrib.admin.views.decorators import staff_member_required
from .forms import ArtikelForm
from .models import UserKelasAccess
from apps.core.rate_limit_global import GlobalRateLimiter
from .models import ChatbotFAQ, ChatbotConversation


# ==================== DATA KELAS ====================
KELAS_DATA = {
    1: {'id': 1, 'nama': 'Positive Discipline 101', 'harga': 149000, 'harga_asli': 299000, 'durasi': '8 jam', 'modul': 5, 'kategori': 'parenting', 'deskripsi': 'Pelajari disiplin positif tanpa hukuman...'},
    2: {'id': 2, 'nama': 'Memahami Dunia Anak (Psikologi Perkembangan)', 'harga': 189000, 'harga_asli': 350000, 'durasi': '10 jam', 'modul': 6, 'kategori': 'psikologi', 'deskripsi': 'Memetakan tahap tumbuh kembang anak...'},
    3: {'id': 3, 'nama': 'Art of Active Listening', 'harga': 99000, 'harga_asli': 189000, 'durasi': '5 jam', 'modul': 4, 'kategori': 'komunikasi', 'deskripsi': 'Tingkatkan kualitas komunikasi...'},
    4: {'id': 4, 'nama': 'Ta\'aruf & Visi Keluarga Sakinah', 'harga': 149000, 'harga_asli': 279000, 'durasi': '6 jam', 'modul': 4, 'kategori': 'pranikah', 'deskripsi': 'Panduan ta\'aruf syar\'i...'},
    5: {'id': 5, 'nama': 'Mendidik Remaja Zaman Now', 'harga': 129000, 'harga_asli': 249000, 'durasi': '7 jam', 'modul': 5, 'kategori': 'parenting', 'deskripsi': 'Strategi menghadapi remaja...'},
    6: {'id': 6, 'nama': 'Emotional Intelligence untuk Anak', 'harga': 159000, 'harga_asli': 299000, 'durasi': '6 jam', 'modul': 4, 'kategori': 'psikologi', 'deskripsi': 'Mengajarkan anak mengelola emosi...'},
}

# ==================== HALAMAN UTAMA ====================
def index(request):
    """Halaman beranda"""
    artikel_terbaru = Artikel.objects.all().order_by('-created_at')[:4]
    context = {
        'artikel_terbaru': artikel_terbaru,
    }
    return render(request, 'core/index.html', context)

# ==================== ARTIKEL ====================
def artikel_list(request):
    """Halaman daftar artikel"""
    artikel_list = Artikel.objects.all().order_by('-created_at')
    kategori = request.GET.get('kategori')
    if kategori:
        artikel_list = artikel_list.filter(kategori=kategori)
    
    context = {
        'artikel_list': artikel_list,
        'kategori_aktif': kategori,
    }
    return render(request, 'core/artikel.html', context)

def artikel_detail(request, slug):
    """Halaman detail artikel"""
    artikel = get_object_or_404(Artikel, slug=slug)
    
    # Hitung estimasi menit membaca
    word_count = len(artikel.konten.split()) if artikel.konten else 0
    menit_membaca = max(1, word_count // 200)
    
    # Tambahkan hitungan dibaca
    artikel.dibaca += 1
    artikel.save(update_fields=['dibaca'])
    
    # Ambil artikel terkait
    related_queryset = Artikel.objects.filter(kategori=artikel.kategori).exclude(id=artikel.id)[:3]
    
    related_articles = []
    for rel in related_queryset:
        rel_word_count = len(rel.konten.split()) if rel.konten else 0
        rel_menit = max(1, rel_word_count // 200)
        rel.menit_membaca = rel_menit
        related_articles.append(rel)
    
    context = {
        'artikel': artikel,
        'menit_membaca': menit_membaca,
        'related_articles': related_articles,
    }
    return render(request, 'core/artikel_detail.html', context)

# ==================== KELAS ONLINE ====================
def kelas(request):
    """Halaman daftar kelas"""
    kelas_data = list(KELAS_DATA.values())
    return render(request, 'core/kelas.html', {'kelas_data': kelas_data})

def kelas_detail(request, kelas_id):
    """Halaman detail kelas"""
    if kelas_id not in KELAS_DATA:
        messages.error(request, 'Kelas tidak ditemukan')
        return redirect('core:kelas')
    
    kelas = KELAS_DATA[kelas_id]
    context = {
        'kelas': kelas,
    }
    return render(request, 'core/kelas_detail.html', context)

# ==================== CHECKOUT & PEMBAYARAN ====================
def checkout(request, kelas_id):
    """Halaman checkout kelas"""
    if kelas_id not in KELAS_DATA:
        messages.error(request, 'Kelas tidak ditemukan')
        return redirect('core:kelas')
    
    kelas = KELAS_DATA[kelas_id]
    
    if request.method == 'POST':
        nama = request.POST.get('nama')
        email = request.POST.get('email')
        whatsapp = request.POST.get('whatsapp')
        
        if not all([nama, email, whatsapp]):
            messages.error(request, 'Harap isi semua data yang diperlukan')
            return redirect('core:checkout', kelas_id=kelas_id)
        
        order_id = f"FML-{uuid.uuid4().hex[:8].upper()}"
        
        order = KelasOrder.objects.create(
            order_id=order_id,
            kelas_id=kelas_id,
            kelas_nama=kelas['nama'],
            kelas_harga=kelas['harga'],
            nama=nama,
            email=email,
            whatsapp=whatsapp,
            payment_method='midtrans',
            payment_gateway='midtrans',
            expires_at=timezone.now() + timedelta(hours=24),
            user=request.user if request.user.is_authenticated else None
        )
        
        result = midtrans_payment.create_transaction(order)
        
        if result['success']:
            order.payment_token = result['token']
            order.payment_url = result['redirect_url']
            order.save()
            
            send_whatsapp_notification(
                whatsapp, nama, 'checkout',
                kelas_nama=kelas['nama'],
                order_id=order_id,
                harga=kelas['harga'],
                payment_url=result['redirect_url']
            )
            
            return redirect(result['redirect_url'])
        else:
            messages.error(request, f'Gagal memproses pembayaran: {result["error"]}')
            return redirect('core:checkout', kelas_id=kelas_id)
    
    context = {
        'kelas': kelas,
        'user': request.user if request.user.is_authenticated else None,
        'midtrans_status': get_midtrans_status(),
        'midtrans_client_key': settings.MIDTRANS_CLIENT_KEY,
        'midtrans_is_production': settings.MIDTRANS_IS_PRODUCTION
    }
    return render(request, 'core/checkout.html', context)

@csrf_exempt
def midtrans_notification(request):
    """Webhook handler untuk Midtrans notification"""
    if request.method == 'POST':
        try:
            notification_data = json.loads(request.body)
            result = midtrans_payment.handle_notification(notification_data)
            
            if result['status'] == 'success':
                order_id = result['order_id']
                
                try:
                    order = KelasOrder.objects.get(transaction_id=order_id)
                    order.status = 'paid'
                    order.save()
                    
                    send_whatsapp_notification(
                        order.whatsapp, order.nama, 'payment_success',
                        kelas_nama=order.kelas_nama,
                        order_id=order.order_id
                    )
                    
                    return JsonResponse({'status': 'ok'})
                except KelasOrder.DoesNotExist:
                    try:
                        order = KelasOrder.objects.get(order_id=order_id)
                        order.status = 'paid'
                        order.save()
                        return JsonResponse({'status': 'ok'})
                    except KelasOrder.DoesNotExist:
                        pass
            
            return JsonResponse({'status': 'ok'})
            
        except Exception as e:
            print(f"Midtrans Notification Error: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    return JsonResponse({'status': 'method not allowed'}, status=405)

def payment_success(request, order_id):
    """Halaman sukses pembayaran"""
    try:
        order = KelasOrder.objects.get(order_id=order_id)
    except KelasOrder.DoesNotExist:
        try:
            order = KelasOrder.objects.get(transaction_id=order_id)
        except KelasOrder.DoesNotExist:
            messages.error(request, 'Order tidak ditemukan')
            return redirect('core:kelas')
    
    if order.status == 'pending':
        order.status = 'paid'
        
        if request.user.is_authenticated and not order.user:
            order.user = request.user
            print(f"User {request.user.username} linked to order {order.order_id}")
        
        order.save()
        # ========== BUKA AKSES KELAS ==========
        if request.user.is_authenticated:
            # Simpan akses ke database
            access, created = UserKelasAccess.objects.get_or_create(
                user=request.user,
                kelas_id=order.kelas_id,
                defaults={
                    'kelas_nama': order.kelas_nama,
                    'order_id': order.order_id,
                    'access_granted': True
                }
            )
            if not created:
                access.access_granted = True
                access.save()
            
            print(f"Akses kelas {order.kelas_nama} diberikan ke {request.user.username}")
        send_whatsapp_notification(
            order.whatsapp, order.nama, 'payment_success',
            kelas_nama=order.kelas_nama,
            order_id=order.order_id
        )
        
        messages.success(request, f'✅ Pembayaran berhasil! Kelas {order.kelas_nama} telah ditambahkan ke "Kelas Saya".')
    
    return render(request, 'core/payment_success.html', {'order': order})

def payment_failed(request, order_id):
    """Halaman gagal pembayaran"""
    order = get_object_or_404(KelasOrder, order_id=order_id)
    return render(request, 'core/payment_failed.html', {'order': order})

@login_required
def my_classes(request):
    """Halaman kelas yang sudah dibeli user"""
    orders = KelasOrder.objects.filter(
        user=request.user,
        status='paid'
    ).order_by('-created_at')
    
    # Ambil akses kelas dari database
    user_access = UserKelasAccess.objects.filter(user=request.user)
    
    # Gabungkan data
    kelas_list = []
    for order in orders:
        kelas_list.append({
            'id': order.kelas_id,
            'nama': order.kelas_nama,
            'harga': order.kelas_harga,
            'created_at': order.created_at,
            'order_id': order.order_id,
            'has_access': True
        })
    
    return render(request, 'core/my_classes.html', {
        'orders': orders,
        'kelas_list': kelas_list
    })



@login_required
def kelas_video(request, kelas_id):
    """Halaman video kelas (terkunci jika belum bayar)"""
    from .models import UserKelasAccess
    
    # Cek apakah user punya akses
    has_access = UserKelasAccess.objects.filter(
        user=request.user,
        kelas_id=kelas_id,
        access_granted=True
    ).exists()
    
    # Atau cek dari order yang paid
    if not has_access:
        has_access = KelasOrder.objects.filter(
            user=request.user,
            kelas_id=kelas_id,
            status='paid'
        ).exists()
    
    # Data kelas
    if kelas_id not in KELAS_DATA:
        messages.error(request, 'Kelas tidak ditemukan')
        return redirect('core:kelas')
    
    kelas = KELAS_DATA[kelas_id]
    
    # Data modul
    modules = [
        {'judul': 'Pengantar Disiplin Positif', 'durasi': '15 menit', 'video_url': 'https://youtu.be/XMJuNRgPo-0?si=Y_AiHPfsMuo1aYmZ'},
        {'judul': 'Memahami Perilaku Anak', 'durasi': '20 menit', 'video_url': 'https://www.youtube.com/embed/video2'},
        {'judul': 'Teknik Komunikasi Efektif', 'durasi': '18 menit', 'video_url': 'https://www.youtube.com/embed/video3'},
        {'judul': 'Mengatasi Tantrum', 'durasi': '22 menit', 'video_url': 'https://www.youtube.com/embed/video4'},
        {'judul': 'Membangun Karakter', 'durasi': '25 menit', 'video_url': 'https://www.youtube.com/embed/video5'},
    ]

    progress_key = f'progress_kelas_{request.user.id}_{kelas_id}'
    completed_modules = request.session.get(progress_key, [])
    modules_completed_count = len(completed_modules)
    total_modules = len(modules)
    progress_percent = int((modules_completed_count / total_modules) * 100) if total_modules > 0 else 0
    
    context = {
        'kelas': kelas,
        'has_access': has_access,
        'modules': modules,
        'progress': progress_percent,
        'modules_completed': modules_completed_count,
        'video_url': modules[0]['video_url'] if has_access else None
    }
    return render(request, 'core/video_kelas.html', context)



# ==================== TA'ARUF ====================
def taaruf(request):
    """Halaman pendaftaran ta'aruf"""
    if request.method == 'POST':
        nama_lengkap = request.POST.get('nama_lengkap')
        jenis_kelamin = request.POST.get('jenis_kelamin')
        tanggal_lahir = request.POST.get('tanggal_lahir') or None
        domisili = request.POST.get('domisili', '')
        email = request.POST.get('email')
        whatsapp = request.POST.get('whatsapp')
        pekerjaan = request.POST.get('pekerjaan', '')
        pendidikan = request.POST.get('pendidikan', '')
        kriteria = request.POST.get('kriteria', '')
        
        pendaftaran = PendaftaranTaaruf.objects.create(
            nama_lengkap=nama_lengkap,
            jenis_kelamin=jenis_kelamin,
            tanggal_lahir=tanggal_lahir,
            domisili=domisili,
            email=email,
            whatsapp=whatsapp,
            pekerjaan=pekerjaan,
            pendidikan=pendidikan,
            kriteria_pasangan=kriteria,
        )
        
        wa_result = send_whatsapp_notification(whatsapp, nama_lengkap, 'taaruf')
        
        if wa_result.get('success'):
            pendaftaran.wa_notification_sent = True
            pendaftaran.save()
        
        try:
            send_mail(
                'Konfirmasi Pendaftaran Ta\'aruf - FamaLine',
                f'Halo {nama_lengkap},\n\nTerima kasih telah mendaftar program ta\'aruf FamaLine. Tim kami akan menghubungi Anda dalam 1x24 jam.\n\nSalam hangat,\nFamaLine',
                settings.DEFAULT_FROM_EMAIL or 'noreply@famaline.com',
                [email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Email error: {e}")
        
        messages.success(request, 'Pendaftaran ta\'aruf berhasil! Silahkan cek WhatsApp untuk info selanjutnya.')
        return redirect('core:taaruf')
    
    return render(request, 'core/taaruf.html')

# ==================== KONSULTASI ====================
def konsultasi(request):
    """Halaman booking konsultasi"""
    if request.method == 'POST':
        nama = request.POST.get('nama')
        email = request.POST.get('email')
        whatsapp = request.POST.get('whatsapp')
        psikolog = request.POST.get('psikolog')
        tanggal = request.POST.get('tanggal')
        waktu = request.POST.get('waktu')
        topik = request.POST.get('topik', '')
        metode = request.POST.get('metode', 'video')
        
        booking = BookingKonsultasi.objects.create(
            nama=nama,
            email=email,
            whatsapp=whatsapp,
            psikolog=psikolog,
            tanggal=tanggal,
            waktu=waktu,
            topik=topik,
            metode=metode,
        )
        
        wa_result = send_whatsapp_notification(
            whatsapp, nama, 'konsultasi',
            psychologist=psikolog,
            date=tanggal,
            time=waktu,
            method=metode
        )
        
        if wa_result.get('success'):
            booking.wa_notification_sent = True
            booking.save()
        
        try:
            send_mail(
                'Konfirmasi Booking Konsultasi - FamaLine',
                f'Halo {nama},\n\nBooking konsultasi Anda telah kami terima.\n\nDetail:\nPsikolog: {psikolog}\nTanggal: {tanggal}\nWaktu: {waktu}\n\nTim kami akan menghubungi Anda via WhatsApp untuk konfirmasi.\n\nSalam,\nFamaLine',
                settings.DEFAULT_FROM_EMAIL or 'noreply@famaline.com',
                [email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Email error: {e}")
        
        messages.success(request, 'Booking konsultasi berhasil! Silahkan cek WhatsApp untuk info selanjutnya.')
        return redirect('core:konsultasi')
    
    return render(request, 'core/konsultasi.html')

# ==================== NEWSLETTER ====================
def subscribe_newsletter(request):
    """Subscribe newsletter"""
    if request.method == 'POST':
        email = request.POST.get('email')
        if email:
            subscriber, created = Subscriber.objects.get_or_create(email=email)
            if created:
                messages.success(request, 'Berlangganan newsletter berhasil!')
            else:
                messages.info(request, 'Email sudah terdaftar.')
        else:
            messages.error(request, 'Email tidak valid.')
        return redirect(request.META.get('HTTP_REFERER', 'core:index'))
    return redirect('core:index')





@login_required
def tambah_artikel(request):
    """Halaman tambah artikel"""
    
    # === BLOKIR ADMIN (sesuai request kamu sebelumnya) ===
    if request.user.is_staff or request.user.is_superuser:
        messages.error(request, 'Admin tidak diizinkan menambahkan artikel melalui halaman ini.')
        return redirect('core:dashboard')  # atau halaman lain

    if request.method == 'POST':
        judul = request.POST.get('judul')
        kategori = request.POST.get('kategori')
        konten = request.POST.get('konten')
        penulis_input = request.POST.get('penulis')

        if not judul or not konten or not kategori:
            messages.error(request, 'Judul, kategori, dan konten wajib diisi')
            return render(request, 'core/tambah_artikel.html')

        # === GENERATE SLUG UNIK (Paling Aman) ===
        base_slug = slugify(judul)
        unique_id = str(uuid.uuid4())[:8]
        slug = f"{base_slug}-{unique_id}"

        # Tentukan penulis
        penulis = penulis_input.strip() if penulis_input and penulis_input.strip() else \
                  (request.user.get_full_name() or request.user.username)

        artikel = Artikel(
            judul=judul,
            slug=slug,
            kategori=kategori,
            konten=konten,
            penulis=penulis,
            
        )

        # Handle gambar
        if request.FILES.get('gambar'):
            artikel.gambar = request.FILES['gambar']

        artikel.save()

        messages.success(request, f'Artikel "{judul}" berhasil ditambahkan!')
        return redirect('core:artikel_detail', slug=artikel.slug)

    return render(request, 'core/tambah_artikel.html')



def manage_artikel_login(request):
    """Halaman login khusus untuk manage artikel"""
    if request.session.get('manage_artikel_auth', False):
        return redirect('core:manage_artikel')
    
    if request.method == 'POST':
        password = request.POST.get('password')
        if password == settings.MANAGE_ARTIKEL_PASSWORD:
            request.session['manage_artikel_auth'] = True
            request.session.set_expiry(3600)
            next_url = request.session.get('manage_artikel_next', 'core:manage_artikel')
            return redirect(next_url)
        else:
            messages.error(request, 'Password salah!')
    
    return render(request, 'core/manage_artikel_login.html')

def manage_artikel_logout(request):
    """Logout dari manage artikel"""
    request.session.pop('manage_artikel_auth', None)
    messages.success(request, 'Anda telah logout')
    return redirect('core:manage_artikel_login')

def manage_artikel(request):
    """Halaman manajemen artikel (tambah, edit, hapus)"""
    if not request.session.get('manage_artikel_auth', False):
        return redirect('core:manage_artikel_login')
    
    if request.method == 'POST':
        judul = request.POST.get('judul')
        kategori = request.POST.get('kategori')
        konten = request.POST.get('konten')
        penulis = request.POST.get('penulis', 'Admin')
        
        if judul and konten:
            base_slug = slugify(judul)
            slug = base_slug
            counter = 1
            while Artikel.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            artikel = Artikel(
                judul=judul,
                slug=slug,
                kategori=kategori,
                konten=konten,
                penulis=penulis
            )
            
            if request.FILES.get('gambar'):
                artikel.gambar = request.FILES['gambar']
            
            artikel.save()
            messages.success(request, f'Artikel "{judul}" berhasil ditambahkan!')
            return redirect('core:manage_artikel')
    
    artikel_list = Artikel.objects.all().order_by('-created_at')
    return render(request, 'core/manage_artikel.html', {'artikel_list': artikel_list})



@csrf_exempt
def get_artikel_json(request, slug):
    """API untuk mengambil data artikel (edit modal)"""
    if not request.session.get('manage_artikel_auth', False):
        return JsonResponse({'success': False, 'error': 'Unauthorized'})
    
    try:
        artikel = Artikel.objects.get(slug=slug)
        return JsonResponse({
            'success': True,
            'slug': artikel.slug,
            'judul': artikel.judul,
            'kategori': artikel.kategori,
            'konten': artikel.konten,
            'penulis': artikel.penulis,
            'gambar_url': artikel.gambar.url if artikel.gambar else None,  # TAMBAHKAN INI
        })
    except Artikel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Artikel tidak ditemukan'})

@csrf_exempt
def edit_artikel_ajax(request, slug):
    """Edit artikel via AJAX (termasuk gambar)"""
    if not request.session.get('manage_artikel_auth', False):
        return JsonResponse({'success': False, 'error': 'Unauthorized'})
    
    if request.method == 'POST':
        try:
            artikel = Artikel.objects.get(slug=slug)
            judul = request.POST.get('edit_judul')
            kategori = request.POST.get('edit_kategori')
            konten = request.POST.get('edit_konten')
            penulis = request.POST.get('edit_penulis')
            delete_image = request.POST.get('delete_image') == 'true'
            
            if judul and konten:
                artikel.judul = judul
                artikel.kategori = kategori
                artikel.konten = konten
                artikel.penulis = penulis or artikel.penulis
                
                # Update slug jika judul berubah
                if artikel.judul != judul:
                    from django.utils.text import slugify
                    base_slug = slugify(judul)
                    new_slug = base_slug
                    counter = 1
                    while Artikel.objects.filter(slug=new_slug).exclude(id=artikel.id).exists():
                        new_slug = f"{base_slug}-{counter}"
                        counter += 1
                    artikel.slug = new_slug
                
                # Handle gambar
                if delete_image:
                    if artikel.gambar:
                        artikel.gambar.delete()
                        artikel.gambar = None
                elif request.FILES.get('edit_gambar'):
                    if artikel.gambar:
                        artikel.gambar.delete()
                    artikel.gambar = request.FILES['edit_gambar']
                
                artikel.save()
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'error': 'Judul dan konten wajib diisi'})
        except Artikel.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Artikel tidak ditemukan'})
    
    return JsonResponse({'success': False, 'error': 'Method not allowed'})


def delete_artikel(request, slug):
    """Hapus artikel"""
    if not request.session.get('manage_artikel_auth', False):
        return redirect('core:manage_artikel_login')
    
    artikel = get_object_or_404(Artikel, slug=slug)
    if request.method == 'POST':
        judul = artikel.judul
        artikel.delete()
        messages.success(request, f'Artikel "{judul}" berhasil dihapus!')
        return redirect('core:manage_artikel')
    
    return redirect('core:manage_artikel')


def rate_limit_status(request):
    """Endpoint untuk cek status rate limit client"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    limiter = GlobalRateLimiter(request)
    remaining = limiter.get_remaining_requests()
    
    return JsonResponse({
        'limit': limiter.settings['MAX_REQUESTS'],
        'remaining': remaining,
        'reset': limiter.settings['TIME_WINDOW'],
        'is_blocked': limiter.is_blocked()[0]
    })


@csrf_exempt
@require_http_methods(["POST"])
def chatbot_api(request):
    """API endpoint untuk chatbot"""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip().lower()
        session_id = data.get('session_id', '')
        
        # Buat session_id jika belum ada
        if not session_id:
            session_id = request.session.get('chatbot_session_id')
            if not session_id:
                session_id = str(uuid.uuid4())
                request.session['chatbot_session_id'] = session_id
        
        # Cari FAQ berdasarkan keywords
        faqs = ChatbotFAQ.objects.filter(is_active=True)
        matched_faq = None
        matched_keywords = []
        
        for faq in faqs:
            keywords = faq.get_keywords_list()
            for keyword in keywords:
                if keyword in message:
                    matched_faq = faq
                    matched_keywords.append(keyword)
                    break
            if matched_faq:
                break
        
        # Response berdasarkan match
        if matched_faq:
            response = matched_faq.answer
            intent = matched_faq.category
        else:
            # Default response
            response = """Maaf, saya kurang paham dengan pertanyaan Anda.

🤖 *Saya bisa membantu:*
""" + "\n".join([f"• {faq.get_category_display()} - {faq.question}" for faq in faqs[:5]]) + """

Ketik *menu* untuk lihat pilihan lengkap atau tanyakan langsung!"""
            intent = 'unknown'
        
        # Simpan percakapan ke database (opsional)
        try:
            ChatbotConversation.objects.create(
                session_id=session_id,
                user=request.user if request.user.is_authenticated else None,
                message=message,
                response=response,
                intent=intent
            )
        except Exception as e:
            print(f"Error saving conversation: {e}")
        
        # Dapatkan menu options untuk quick reply
        menu_options = []
        for faq in faqs[:6]:
            menu_options.append({
                'category': faq.category,
                'button_text': faq.button_text or faq.question[:30],
                'icon': faq.button_icon or self.get_category_icon(faq.category),
                'keywords': faq.get_keywords_list()
            })
        
        return JsonResponse({
            'success': True,
            'response': response,
            'intent': intent,
            'session_id': session_id,
            'menu_options': menu_options
        })
        
    except Exception as e:
        print(f"Chatbot API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def get_category_icon(category):
    icons = {
        'kelas': '📚',
        'konsultasi': '👩‍⚕️',
        'taaruf': '💍',
        'artikel': '📖',
        'harga': '💰',
        'akun': '🔐',
        'umum': '🤖'
    }
    return icons.get(category, '🤖')


def get_chatbot_faqs(request):
    """API untuk mengambil data FAQ (untuk inisialisasi frontend)"""
    faqs = ChatbotFAQ.objects.filter(is_active=True).order_by('order')[:8]
    
    data = []
    for faq in faqs:
        data.append({
            'id': faq.id,
            'category': faq.get_category_display(),
            'category_key': faq.category,
            'button_text': faq.button_text or faq.question[:30],
            'button_icon': faq.button_icon or get_category_icon(faq.category),
            'keywords': faq.get_keywords_list(),
            'question': faq.question,
            'answer': faq.answer
        })
    
    return JsonResponse({
        'success': True,
        'faqs': data
    })
