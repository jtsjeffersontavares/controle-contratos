from django.contrib.auth.mixins import UserPassesTestMixin

EDIT_GROUPS = {"Administrador", "Gestor", "Fiscal"}
MANAGEMENT_GROUPS = {"Administrador", "Gestor"}
ADMIN_GROUPS = {"Administrador"}


def _has_group(user, groups):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name__in=groups).exists())
    )


def user_can_edit(user):
    return _has_group(user, EDIT_GROUPS) or bool(user and user.is_staff)


def user_can_manage(user):
    return _has_group(user, MANAGEMENT_GROUPS) or bool(user and user.is_staff)


def user_is_admin(user):
    return _has_group(user, ADMIN_GROUPS) or bool(user and user.is_staff)


class EditorRequiredMixin(UserPassesTestMixin):
    permission_denied_message = "Seu perfil possui acesso somente para consulta."

    def test_func(self):
        return user_can_edit(self.request.user)


class ManagerRequiredMixin(UserPassesTestMixin):
    permission_denied_message = "A operação exige perfil de Gestor ou Administrador."

    def test_func(self):
        return user_can_manage(self.request.user)


class AdminRequiredMixin(UserPassesTestMixin):
    permission_denied_message = "A operação exige perfil de Administrador."

    def test_func(self):
        return user_is_admin(self.request.user)
