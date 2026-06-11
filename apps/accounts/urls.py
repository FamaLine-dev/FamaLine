from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Regular auth
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    # Forgot Password
    path('forgot-password/', views.forgot_password_request, name='forgot_password'),
    path('reset-password/<uidb64>/<token>/', views.reset_password_confirm, name='reset_password_confirm'),

    # WhatsApp OTP endpoints
    path('send-wa-otp/', views.send_wa_otp, name='send_wa_otp'),
    path('verify-wa-otp/', views.verify_wa_otp, name='verify_wa_otp'),
    path('resend-wa-otp/', views.resend_wa_otp, name='resend_wa_otp'),
    path('cancel-wa-login/', views.cancel_wa_login, name='cancel_wa_login'),
    
    # PIN Security endpoints
    path('set-security-pin/', views.set_security_pin, name='set_security_pin'),
    path('verify-security-pin/', views.verify_security_pin, name='verify_security_pin'),
    # Forgot PIN endpoints
    path('forgot-pin/', views.forgot_pin_request, name='forgot_pin_request'),
    path('forgot-pin-verify/', views.forgot_pin_verify_otp, name='forgot_pin_verify'),
    path('forgot-pin-set/', views.forgot_pin_set_new, name='forgot_pin_set_new'),
    # Tambahkan di urlpatterns
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/change-pin/', views.change_pin, name='change_pin'),
    path('profile/delete/', views.delete_account, name='delete_account'),
]
