from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def es_invitado(request):
    return bool(request.session.get('is_guest'))


def bloquear_invitados(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if es_invitado(request):
            messages.error(request, 'Acción no permitida en modo invitado.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper
