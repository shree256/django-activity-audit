from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tests.publications.views import AuthorViewSet, BookViewSet

router = DefaultRouter()
router.register(r"books", BookViewSet)
router.register(r"authors", AuthorViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
]
