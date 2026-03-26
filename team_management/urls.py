"""
URL configuration for team_management project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from mlb import views as mlb_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/rosters', mlb_views.api_rosters, name='api_rosters_no_slash'),
    path('api/rosters/', mlb_views.api_rosters, name='api_rosters'),
    path('api/rosters/<str:team_code>', mlb_views.api_team_roster, name='api_team_roster_no_slash'),
    path('api/rosters/<str:team_code>/', mlb_views.api_team_roster, name='api_team_roster'),
    path('api/teams', mlb_views.api_teams, name='api_teams_no_slash'),
    path('api/teams/', mlb_views.api_teams, name='api_teams'),
    path('api/teams/<str:team_code>/players', mlb_views.api_team_players, name='api_team_players_no_slash'),
    path('api/teams/<str:team_code>/players/', mlb_views.api_team_players, name='api_team_players'),
    path(
        'api/teams/<str:team_code>/players/<str:player_id>',
        mlb_views.api_team_player_detail,
        name='api_team_player_detail_no_slash',
    ),
    path(
        'api/teams/<str:team_code>/players/<str:player_id>/',
        mlb_views.api_team_player_detail,
        name='api_team_player_detail',
    ),
    path('', include('roster.urls')),
    path('mlb/', include('mlb.urls')),
]
