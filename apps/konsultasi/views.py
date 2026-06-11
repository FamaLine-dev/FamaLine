from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings

# Hapus import login_required untuk sementara
# from django.contrib.auth.decorators import login_required

def konsultasi(request):
    """Halaman booking konsultasi"""
    if request.method == 'POST':
        psikolog = request.POST.get('psikolog')
        nama = request.POST.get('nama')
        email = request.POST.get('email')
        whatsapp = request.POST.get('whatsapp')
        tanggal = request.POST.get('tanggal')
        waktu = request.POST.get('waktu')
        topik = request.POST.get('topik')
        metode = request.POST.get('metode')
        
        # Simpan ke session
        request.session['konsultasi_data'] = {
            'psikolog': psikolog,
            'nama': nama,
            'email': email,
            'whatsapp': whatsapp,
            'tanggal': tanggal,
            'waktu': waktu,
            'topik': topik,
            'metode': metode,
        }
        
        messages.success(request, 'Booking konsultasi berhasil! Tim kami akan menghubungi Anda dalam 1x24 jam.')
        return redirect('core:konsultasi')
    
    return render(request, 'konsultasi/konsultasi.html')
