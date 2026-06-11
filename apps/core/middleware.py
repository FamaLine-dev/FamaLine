from django.shortcuts import redirect

class ManageArtikelAuthMiddleware:
    """Middleware untuk proteksi halaman manage artikel dengan password"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        protected_paths = ['/manage-artikel/', '/get-artikel/', '/edit-artikel/', '/delete-artikel/']
        
        # Kecualikan halaman login
        if request.path == '/manage-artikel/login/':
            return self.get_response(request)
        
        is_protected = any(request.path.startswith(path) for path in protected_paths)
        
        if is_protected and not request.session.get('manage_artikel_auth', False):
            request.session['manage_artikel_next'] = request.path
            return redirect('core:manage_artikel_login')
        
        return self.get_response(request)
