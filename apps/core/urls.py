from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.index, name='index'),
    path('artikel/', views.artikel_list, name='artikel_list'),
    path('artikel/<slug:slug>/', views.artikel_detail, name='artikel_detail'),
    path('taaruf/', views.taaruf, name='taaruf'),
    path('kelas/', views.kelas, name='kelas'),
    path('kelas/<int:kelas_id>/', views.kelas_detail, name='kelas_detail'),  # ← TAMBAHKAN INI
    path('checkout/<int:kelas_id>/', views.checkout, name='checkout'),
    path('payment/success/<str:order_id>/', views.payment_success, name='payment_success'),
    path('payment/failed/<str:order_id>/', views.payment_failed, name='payment_failed'),
    path('api/midtrans/notification/', views.midtrans_notification, name='midtrans_notification'),
    path('my-classes/', views.my_classes, name='my_classes'),
    path('konsultasi/', views.konsultasi, name='konsultasi'),
    path('subscribe/', views.subscribe_newsletter, name='subscribe'),
    # Manajemen Artikel (dengan password)
    path('manage-artikel/login/', views.manage_artikel_login, name='manage_artikel_login'),
    path('manage-artikel/logout/', views.manage_artikel_logout, name='manage_artikel_logout'),
    path('manage-artikel/', views.manage_artikel, name='manage_artikel'),
    path('get-artikel/<slug:slug>/', views.get_artikel_json, name='get_artikel_json'),
    path('edit-artikel/<slug:slug>/', views.edit_artikel_ajax, name='edit_artikel_ajax'),
    path('delete-artikel/<slug:slug>/', views.delete_artikel, name='delete_artikel'),
    path('kelas/video/<int:kelas_id>/', views.kelas_video, name='kelas_video'),
    path('api/rate-limit-status/', views.rate_limit_status, name='rate_limit_status'),
    path('api/chatbot/', views.chatbot_api, name='chatbot_api'),
    path('api/chatbot-faqs/', views.get_chatbot_faqs, name='chatbot_faqs'),
]
