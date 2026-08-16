from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path

urlpatterns = [
    path("admin/", admin.site.urls),
    re_path(
        r"^login/?$",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    re_path(r"^logout/?$", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("contracts.urls")),
]
