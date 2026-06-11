# apps/core/rate_limit_global.py

from django.core.cache import cache
from django.conf import settings
from django.http import JsonResponse
import time
import hashlib
import hmac
from functools import wraps

class GlobalRateLimiter:
    """Rate limiter global untuk semua request"""
    
    def __init__(self, request):
        self.request = request
        self.settings = getattr(settings, 'GLOBAL_RATE_LIMIT', {
            'MAX_REQUESTS': 100,           # Maksimal request
            'TIME_WINDOW': 60,             # Dalam 60 detik
            'BLOCK_DURATION': 300,         # Blokir 5 menit jika melebihi
        })
    
    def get_client_fingerprint(self):
        """Buat fingerprint unik client (IP + User Agent)"""
        ip = self.get_client_ip()
        user_agent = self.request.META.get('HTTP_USER_AGENT', 'unknown')
        
        # Kombinasi untuk identifikasi unik
        fingerprint_data = f"{ip}|{user_agent}"
        
        # Hash dengan secret key
        fingerprint = hmac.new(
            settings.SECRET_KEY.encode(),
            fingerprint_data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return fingerprint
    
    def get_client_ip(self):
        """Dapatkan IP client yang sebenarnya"""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip
    
    def get_keys(self):
        """Buat keys untuk cache"""
        fingerprint = self.get_client_fingerprint()
        return {
            'counter': f"global_rate:{fingerprint}:counter",
            'window_start': f"global_rate:{fingerprint}:window_start",
            'blocked': f"global_rate:{fingerprint}:blocked",
        }
    
    def is_blocked(self):
        """Cek apakah client sedang diblokir"""
        keys = self.get_keys()
        blocked_until = cache.get(keys['blocked'])
        
        if blocked_until and time.time() < blocked_until:
            remaining = int(blocked_until - time.time())
            return True, remaining
        
        if blocked_until:
            cache.delete(keys['blocked'])
            cache.delete(keys['counter'])
            cache.delete(keys['window_start'])
        
        return False, 0
    
    def check_and_increment(self):
        """
        Cek rate limit dan increment counter
        Returns: (allowed, wait_seconds, current_count)
        """
        keys = self.get_keys()
        current_time = time.time()
        
        # Cek blokir
        is_blocked, remaining = self.is_blocked()
        if is_blocked:
            return False, remaining, 0
        
        # Dapatkan window start
        window_start = cache.get(keys['window_start'])
        
        # Inisialisasi window baru jika belum ada atau sudah lewat
        if not window_start or current_time - window_start > self.settings['TIME_WINDOW']:
            cache.set(keys['window_start'], current_time, self.settings['TIME_WINDOW'])
            cache.set(keys['counter'], 1, self.settings['TIME_WINDOW'])
            return True, 0, 1
        
        # Increment counter dalam window yang sama
        counter = cache.get(keys['counter'], 0)
        
        if counter >= self.settings['MAX_REQUESTS']:
            # Blokir client
            block_until = current_time + self.settings['BLOCK_DURATION']
            cache.set(keys['blocked'], block_until, self.settings['BLOCK_DURATION'])
            cache.delete(keys['counter'])
            cache.delete(keys['window_start'])
            return False, self.settings['BLOCK_DURATION'], counter
        
        # Increment counter
        new_counter = counter + 1
        cache.set(keys['counter'], new_counter, self.settings['TIME_WINDOW'])
        
        # Hitung sisa waktu
        elapsed = current_time - window_start
        remaining_window = int(self.settings['TIME_WINDOW'] - elapsed)
        
        return True, remaining_window, new_counter
    
    def get_remaining_requests(self):
        """Dapatkan sisa request yang masih bisa dilakukan"""
        keys = self.get_keys()
        window_start = cache.get(keys['window_start'])
        
        if not window_start:
            return self.settings['MAX_REQUESTS']
        
        counter = cache.get(keys['counter'], 0)
        remaining = self.settings['MAX_REQUESTS'] - counter
        
        return max(0, remaining)
    
    def reset(self):
        """Reset rate limit untuk client"""
        keys = self.get_keys()
        cache.delete(keys['counter'])
        cache.delete(keys['window_start'])
        cache.delete(keys['blocked'])


# Decorator untuk rate limit global
def global_rate_limit(view_func):
    """Decorator untuk menerapkan rate limit global pada view"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        limiter = GlobalRateLimiter(request)
        
        # Cek rate limit
        allowed, wait_seconds, current_count = limiter.check_and_increment()
        
        if not allowed:
            return JsonResponse({
                'success': False,
                'error': f'Terlalu banyak request. Coba lagi dalam {wait_seconds} detik.',
                'wait_seconds': wait_seconds,
                'limit': limiter.settings['MAX_REQUESTS'],
                'remaining': 0,
                'retry_after': wait_seconds
            }, status=429)
        
        # Eksekusi view
        response = view_func(request, *args, **kwargs)
        
        # Tambahkan header rate limit
        remaining = limiter.get_remaining_requests()
        response['X-RateLimit-Limit'] = str(limiter.settings['MAX_REQUESTS'])
        response['X-RateLimit-Remaining'] = str(remaining)
        response['X-RateLimit-Reset'] = str(wait_seconds)
        
        return response
    
    return wrapper


class GlobalRateLimitMiddleware:
    """Middleware untuk rate limit global"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = [
            '/static/',
            '/media/',
            '/admin/login/',
            '/social-auth/',
        ]
    
    def __call__(self, request):
        # Skip untuk static files dan exempt paths
        for path in self.exempt_paths:
            if request.path.startswith(path):
                return self.get_response(request)
        
        # Skip untuk method OPTIONS (CORS preflight)
        if request.method == 'OPTIONS':
            return self.get_response(request)
        
        # Terapkan rate limit
        limiter = GlobalRateLimiter(request)
        allowed, wait_seconds, current_count = limiter.check_and_increment()
        
        if not allowed:
            return JsonResponse({
                'success': False,
                'error': f'Terlalu banyak request. Coba lagi dalam {wait_seconds} detik.',
                'wait_seconds': wait_seconds,
                'retry_after': wait_seconds
            }, status=429)
        
        response = self.get_response(request)
        
        # Tambahkan header
        remaining = limiter.get_remaining_requests()
        response['X-RateLimit-Limit'] = str(limiter.settings['MAX_REQUESTS'])
        response['X-RateLimit-Remaining'] = str(remaining)
        response['X-RateLimit-Reset'] = str(wait_seconds)
        
        return response
