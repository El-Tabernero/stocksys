from django import template

register = template.Library()


@register.filter
def currency_ar(value):
    """1200000 → 1.200.000,00"""
    try:
        parts = str(value).split('.')
    except (ValueError, TypeError):
        return value
    entero = parts[0].replace('-', '').replace(',', '')
    signo = '-' if str(value).startswith('-') else ''
    decimales = parts[1][:2].ljust(2, '0') if len(parts) > 1 else '00'
    formatted = ''
    for i, ch in enumerate(reversed(entero)):
        if i and i % 3 == 0:
            formatted = '.' + formatted
        formatted = ch + formatted
    return f'{signo}{formatted},{decimales}'


@register.filter
def get_item(dictionary, key):
    try:
        return dictionary.get(key, {}).get('unidades', 0)
    except AttributeError:
        return dictionary.get(key, 0)
