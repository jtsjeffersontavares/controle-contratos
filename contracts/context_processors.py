from django.conf import settings

from .permissions import user_can_edit, user_can_manage, user_is_admin


def system_context(request):
    user = getattr(request, "user", None)
    return {
        "system_name": settings.SYSTEM_NAME,
        "system_organization": settings.SYSTEM_ORGANIZATION,
        "can_edit": user_can_edit(user),
        "can_manage": user_can_manage(user),
        "is_system_admin": user_is_admin(user),
    }
