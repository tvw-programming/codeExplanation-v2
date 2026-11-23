from django.urls import path, include
from . import views

urlpatterns = [
    path('blog/', include('blog.urls')),
    path('home/', views.home),
]
