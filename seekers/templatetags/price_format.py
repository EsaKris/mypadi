from django import template

register = template.Library()

def format_short(value, suffix):
    formatted = f"{value:.1f}".rstrip('0').rstrip('.')
    return f"{formatted}{suffix}"

@register.filter
def short_price(value):
    try:
        value = float(value)
    except (ValueError, TypeError):
        return value

    if value >= 1_000_000:
        return format_short(value / 1_000_000, 'm')
    elif value >= 1_000:
        return format_short(value / 1_000, 'k')
    else:
        return str(int(value))
