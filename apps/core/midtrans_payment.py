# apps/core/midtrans_payment.py

import midtransclient
import uuid
from django.conf import settings
from datetime import datetime

class MidtransPayment:
    """Class untuk handle Midtrans Payment Gateway"""
    
    def __init__(self):
        """Initialize Midtrans client berdasarkan environment"""
        self.is_production = settings.MIDTRANS_IS_PRODUCTION
        
        if self.is_production:
            # Production Mode
            self.core = midtransclient.CoreApi(
                is_production=True,
                server_key=settings.MIDTRANS_SERVER_KEY,
                client_key=settings.MIDTRANS_CLIENT_KEY
            )
            self.snap = midtransclient.Snap(
                is_production=True,
                server_key=settings.MIDTRANS_SERVER_KEY,
                client_key=settings.MIDTRANS_CLIENT_KEY
            )
        else:
            # Sandbox Mode
            self.core = midtransclient.CoreApi(
                is_production=False,
                server_key=settings.MIDTRANS_SERVER_KEY,
                client_key=settings.MIDTRANS_CLIENT_KEY
            )
            self.snap = midtransclient.Snap(
                is_production=False,
                server_key=settings.MIDTRANS_SERVER_KEY,
                client_key=settings.MIDTRANS_CLIENT_KEY
            )
    
    def create_transaction(self, order):
        """
        Membuat transaksi di Midtrans
        
        Args:
            order: Objek KelasOrder
        
        Returns:
            dict: {'success': bool, 'token': str, 'redirect_url': str, 'error': str}
        """
        try:
            # Generate order ID
            order_id = f"ASUH-{order.id}-{uuid.uuid4().hex[:6].upper()}"
            
            # Prepare parameter untuk Snap
            parameter = {
                "transaction_details": {
                    "order_id": order_id,
                    "gross_amount": int(order.kelas_harga)
                },
                "credit_card": {
                    "secure": True
                },
                "customer_details": {
                    "first_name": order.nama[:20],
                    "last_name": "",
                    "email": order.email,
                    "phone": order.whatsapp,
                    "billing_address": {
                        "first_name": order.nama[:20],
                        "last_name": "",
                        "email": order.email,
                        "phone": order.whatsapp,
                        "country_code": "IDN"
                    }
                },
                "item_details": [
                    {
                        "id": str(order.kelas_id),
                        "price": int(order.kelas_harga),
                        "quantity": 1,
                        "name": order.kelas_nama[:50]
                    }
                ],
                "callbacks": {
                    "finish": f"{settings.PAYMENT_SUCCESS_URL}{order.order_id}/",
                    "error": f"{settings.PAYMENT_FAILED_URL}{order.order_id}/"
                }
            }
            
            # Create Snap Transaction
            transaction = self.snap.create_transaction(parameter)
            
            # Update order dengan token
            order.payment_token = transaction.get('token')
            order.payment_url = transaction.get('redirect_url')
            order.transaction_id = order_id
            order.save()
            
            return {
                'success': True,
                'token': transaction.get('token'),
                'redirect_url': transaction.get('redirect_url')
            }
            
        except Exception as e:
            print(f"Midtrans Error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_charge(self, order, payment_type='bank_transfer', bank='bca'):
        """
        Membuat charge langsung (tanpa Snap) untuk payment channel tertentu
        
        Args:
            order: Objek KelasOrder
            payment_type: jenis pembayaran ('bank_transfer', 'credit_card', 'qris', 'gopay')
            bank: bank tujuan untuk bank_transfer ('bca', 'mandiri', 'bni', 'bri')
        
        Returns:
            dict: response dari Midtrans
        """
        try:
            order_id = f"ASUH-{order.id}-{uuid.uuid4().hex[:6].upper()}"
            
            if payment_type == 'bank_transfer':
                parameter = {
                    "payment_type": payment_type,
                    "transaction_details": {
                        "order_id": order_id,
                        "gross_amount": int(order.kelas_harga)
                    },
                    "customer_details": {
                        "first_name": order.nama[:20],
                        "email": order.email,
                        "phone": order.whatsapp
                    },
                    "item_details": [
                        {
                            "id": str(order.kelas_id),
                            "price": int(order.kelas_harga),
                            "quantity": 1,
                            "name": order.kelas_nama[:50]
                        }
                    ],
                    "bank_transfer": {
                        "bank": bank,
                        "va_number": f"8888{order.id}{order.kelas_id}"
                    }
                }
            elif payment_type == 'qris':
                parameter = {
                    "payment_type": "qris",
                    "transaction_details": {
                        "order_id": order_id,
                        "gross_amount": int(order.kelas_harga)
                    },
                    "customer_details": {
                        "first_name": order.nama[:20],
                        "email": order.email,
                        "phone": order.whatsapp
                    },
                    "qris": {
                        "acquirer": "gopay"
                    }
                }
            elif payment_type == 'gopay':
                parameter = {
                    "payment_type": "gopay",
                    "transaction_details": {
                        "order_id": order_id,
                        "gross_amount": int(order.kelas_harga)
                    },
                    "customer_details": {
                        "first_name": order.nama[:20],
                        "email": order.email,
                        "phone": order.whatsapp
                    }
                }
            else:
                # Credit Card
                parameter = {
                    "payment_type": "credit_card",
                    "transaction_details": {
                        "order_id": order_id,
                        "gross_amount": int(order.kelas_harga)
                    },
                    "credit_card": {
                        "secure": True
                    }
                }
            
            # Charge transaction
            transaction = self.core.charge(parameter)
            
            # Update order
            order.transaction_id = order_id
            order.payment_token = transaction.get('transaction_id', '')
            order.save()
            
            return {
                'success': True,
                'data': transaction
            }
            
        except Exception as e:
            print(f"Midtrans Charge Error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_status(self, order_id):
        """
        Mendapatkan status transaksi
        
        Args:
            order_id: Order ID dari Midtrans
        
        Returns:
            dict: status transaksi
        """
        try:
            status = self.core.transactions.status(order_id)
            return status
        except Exception as e:
            print(f"Midtrans Status Error: {str(e)}")
            return None
    
    def cancel_transaction(self, order_id):
        """Membatalkan transaksi"""
        try:
            result = self.core.transactions.cancel(order_id)
            return result
        except Exception as e:
            print(f"Midtrans Cancel Error: {str(e)}")
            return None
    
    def handle_notification(self, notification_data):
        """
        Handle notifikasi dari Midtrans
        
        Args:
            notification_data: dict dari request body
        
        Returns:
            dict: status pembayaran
        """
        try:
            # Verifikasi signature key (untuk keamanan)
            order_id = notification_data.get('order_id')
            transaction_status = notification_data.get('transaction_status')
            fraud_status = notification_data.get('fraud_status')
            payment_type = notification_data.get('payment_type')
            gross_amount = notification_data.get('gross_amount')
            
            if transaction_status == 'capture':
                if fraud_status == 'accept':
                    return {
                        'order_id': order_id,
                        'status': 'success',
                        'message': 'Pembayaran berhasil'
                    }
                else:
                    return {
                        'order_id': order_id,
                        'status': 'challenge',
                        'message': 'Pembayaran perlu verifikasi'
                    }
            elif transaction_status == 'settlement':
                return {
                    'order_id': order_id,
                    'status': 'success',
                    'message': 'Pembayaran berhasil'
                }
            elif transaction_status == 'pending':
                return {
                    'order_id': order_id,
                    'status': 'pending',
                    'message': 'Menunggu pembayaran'
                }
            elif transaction_status in ['deny', 'cancel', 'expire']:
                return {
                    'order_id': order_id,
                    'status': 'failed',
                    'message': 'Pembayaran gagal/kadaluarsa'
                }
            else:
                return {
                    'order_id': order_id,
                    'status': 'unknown',
                    'message': 'Status tidak diketahui'
                }
                
        except Exception as e:
            print(f"Midtrans Notification Error: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }


# Instance global
midtrans_payment = MidtransPayment()


def get_midtrans_status():
    """Mendapatkan status Midtrans (Sandbox/Production)"""
    if settings.MIDTRANS_IS_PRODUCTION:
        return {
            'mode': 'Production',
            'server_key': settings.MIDTRANS_SERVER_KEY[:10] + '...',
            'client_key': settings.MIDTRANS_CLIENT_KEY[:10] + '...'
        }
    else:
        return {
            'mode': 'Sandbox',
            'server_key': settings.MIDTRANS_SERVER_KEY[:10] + '...',
            'client_key': settings.MIDTRANS_CLIENT_KEY[:10] + '...'
        }
