# core/templatetags/query_helpers.py
"""
Template tags for manipulating query string parameters cleanly.
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """
    Replaces or adds query string parameters to the current request URL,
    preserving existing parameters while stripping any that are set to None or empty string.

    Usage:
        {% load query_helpers %}
        <a href="?{% url_replace page=page_obj.next_page_number %}">Next</a>
    """
    request = context.get("request")
    if not request:
        return ""
    query = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            query.pop(key, None)
        else:
            query[key] = str(value)
    return query.urlencode()


def is_truthy(value) -> bool:
    """
    Returns True if value represents a truthy boolean string or integer.
    Handles 'true', 'True', '1', 1, True, 'yes', 'on', etc.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "on")


@register.filter(name="is_truthy")
def is_truthy_filter(value) -> bool:
    """Template filter to check if a string or variable is truthy."""
    return is_truthy(value)

