from datetime import datetime

from django.utils import timezone


def guest(request):
    es_guest = bool(request.session.get('is_guest'))
    restante = None
    expira = request.session.get('guest_expires_at')
    if es_guest and expira:
        try:
            expira_dt = datetime.fromisoformat(expira)
            if timezone.is_naive(expira_dt):
                expira_dt = timezone.make_aware(expira_dt)
        except (ValueError, TypeError):
            expira_dt = None
        if expira_dt:
            restante = max(0, int((expira_dt - timezone.now()).total_seconds()))
    return {
        'es_invitado': es_guest,
        'guest_restante_seg': restante,
    }
