from django.urls import path

from . import views

app_name = 'roster'

urlpatterns = [
    path('', views.PlayerListView.as_view(), name='player_list'),
    path('players/add/', views.PlayerCreateView.as_view(), name='player_add'),
    path('players/<int:pk>/', views.PlayerDetailView.as_view(), name='player_detail'),
    path('players/<int:pk>/edit/', views.PlayerUpdateView.as_view(), name='player_edit'),
    path('players/<int:pk>/kick-out/', views.player_kick_out, name='player_kick_out'),
    path('players/<int:pk>/contract/', views.contract_edit, name='contract_edit'),
]
