# apps/core/rate_limit_per_endpoint.py

from django.core.cache import cache
from django.conf import settings
from django.http import JsonResponse
import time
import hashlib
import hmac
from functools import wraps

class EndpointRateLimiter:
    """Rate limiter per endpoint"""
    
    def __init__(self, request, endpoint_name):
        self.request = request
        self.endpoint_name = endpoint_name
        self.settings = settings.ENDPOINT_RATE_LIMITS.get(endpoint_name, {
            'max': 30,
            'window': 60,
            'block': 300
        })
    
    def get_client_id(self):
        """Dapatkan ID client yang unik"""
        ip = self.get_client_ip()
        user_agent = self.request.META.get('HTTP_USER_AGENT', 'unknown')
        
        # Untuk endpoint yang memerlukan user login
        if self.request.user.is_authenticated:
            return f"user_{self.request.user.id}"
        
        # Untuk endpoint umum
        fingerprint_data = f"{ip}|{user_agent}"
        fingerprint = hmac.new(
            settings.SECRET_KEY.encode(),
            fingerprint_data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return fingerprint
    
    def get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip
    
    def get_keys(self):
        client_id = self.get_client_id()
        return {
            'counter': f"endpoint_rate:{self.endpoint_name}:{client_id}:counter",
            'window_start': f"endpoint_rate:{self.endpoint_name}:{client_id}:window_start",
            'blocked': f"endpoint_rate:{self.endpoint_name}:{client_id}:blocked",
        }
    
    def is_allowed(self):
        """Cek apakah request diizinkan"""
        keys = self.get_keys()
        current_time = time.time()
        
        # Cek blokir
        blocked_until = cache.get(keys['blocked'])
        if blocked_until and current_time < blocked_until:
            remaining = int(blocked_until - current_time)
            return False, remaining, 0
        
        # Dapatkan window start
        window_start = cache.get(keys['window_start'])
        
        # Inisialisasi window baru
        if not window_start or current_time - window_start > self.settings['window']:
            cache.set(keys['window_start'], current_time, self.settings['window'])
            cache.set(keys['counter'], 1, self.settings['window'])
            return True, 0, 1
        
        # Increment counter
        counter = cache.get(keys['counter'], 0)
        
        if counter >= self.settings['max']:
            # Blokir client
            block_until = current_time + self.settings['block']
            cache.set(keys['blocked'], block_until, self.settings['block'])
            cache.delete(keys['counter'])
            cache.delete(keys['window_start'])
            return False, self.settings['block'], counter
        
        new_counter = counter + 1
        cache.set(keys['counter'], new_counter, self.settings['window'])
        
        elapsed = current_time - window_start
        remaining_window = int(self.settings['window'] - elapsed)
        
        return True, remaining_window, new_counter


def rate_limit(endpoint_name):
    """Decorator untuk rate limit per endpoint"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            limiter = EndpointRateLimiter(request, endpoint_name)
            allowed, wait_seconds, count = limiter.is_allowed()
            
            if not allowed:
                return JsonResponse({
                    'success': False,
                    'error': f'Terlalu banyak percobaan. Coba lagi dalam {wait_seconds} detik.',
                    'wait_seconds': wait_seconds,
                    'retry_after': wait_seconds
                }, status=429)
            
            response = view_func(request, *args, **kwargs)
            
            # Tambahkan header
            response['X-RateLimit-Endpoint'] = endpoint_name
            response['X-RateLimit-Remaining'] = str(limiter.settings['max'] - count)
            
            return response
        return wrapper
    return decorator
