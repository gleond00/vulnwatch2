# project/urls.py  (ajusta el nombre del paquete raíz si no es "project")
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # Raíz -> Admin (tu “interfaz temporal”)
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", admin.site.urls),

    # API
    path("api/v1/", include(("core.urls", "core"), namespace="api-v1")),
]
