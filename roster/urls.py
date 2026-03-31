from django.urls import path

from . import views

app_name = 'roster'

urlpatterns = [
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),
    path('api/auth/me/', views.api_me, name='api_me'),
    path('api/team-image', views.api_team_image, name='api_team_image_no_slash'),
    path('api/team-image/', views.api_team_image, name='api_team_image'),
    path('api/players/', views.api_players, name='api_players'),
    path('api/players/<int:pk>/', views.api_player_detail, name='api_player_detail'),
    path('', views.PlayerListView.as_view(), name='player_list'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('players/add/', views.PlayerCreateView.as_view(), name='player_add'),
    path('players/<int:pk>/', views.PlayerDetailView.as_view(), name='player_detail'),
    path('players/<int:pk>/edit/', views.PlayerUpdateView.as_view(), name='player_edit'),
    path('players/<int:pk>/kick-out/', views.player_kick_out, name='player_kick_out'),
    path('players/<int:pk>/contract/', views.contract_edit, name='contract_edit'),
]
