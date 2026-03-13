from django.urls import path

from . import views

app_name = 'mlb'

urlpatterns = [
    path('', views.player_search, name='search'),
    path('player/<int:pk>/', views.player_detail, name='player_detail'),
]
