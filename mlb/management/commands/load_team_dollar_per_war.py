import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mlb.models import MLBApiTeamDollarPerWar


DEFAULT_SOURCE_FILE = 'team_dollar_per_war.csv'


def _to_float(value):
    if value in (None, ''):
        return None
    return float(value)


def _to_int(value):
    if value in (None, ''):
        return None
    return int(value)


class Command(BaseCommand):
    help = 'Load team-level $/WAR rows from team_dollar_per_war.csv into a dedicated table.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing team $/WAR rows before loading.',
        )
        parser.add_argument(
            '--base-dir',
            help='Optional base directory containing the data/ folder.',
        )

    def handle(self, *args, **options):
        base_dir = Path(options['base_dir']) if options.get('base_dir') else Path(settings.BASE_DIR)
        csv_path = base_dir / 'data' / DEFAULT_SOURCE_FILE
        if not csv_path.exists():
            raise CommandError(f'Team $/WAR CSV not found: {csv_path}')

        team_rows = self._load_csv(csv_path)

        with transaction.atomic():
            if options['replace']:
                deleted_count, _ = MLBApiTeamDollarPerWar.objects.all().delete()
                self.stdout.write(f'Deleted {deleted_count} existing team $/WAR rows.')

            if team_rows:
                MLBApiTeamDollarPerWar.objects.bulk_create(
                    team_rows,
                    batch_size=500,
                    update_conflicts=True,
                    unique_fields=['team'],
                    update_fields=[
                        'avg_payroll_m_3yr',
                        'avg_batting_war_3yr',
                        'avg_pitching_war_3yr',
                        'avg_team_war_3yr',
                        'n_years',
                        'avg_team_war_3yr_safe',
                        'dollar_per_war_millions',
                        'dollar_per_war',
                        'updated_at',
                    ],
                )

        self.stdout.write(
            self.style.SUCCESS(f'Loaded or updated {len(team_rows)} team $/WAR rows.')
        )

    def _load_csv(self, csv_path):
        objects = []
        seen_teams = set()
        with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for line_number, raw in enumerate(reader, start=2):
                team = (raw.get('Team') or '').strip().upper()
                if not team:
                    raise CommandError(f'Missing Team value on line {line_number}: {csv_path}')
                if team in seen_teams:
                    raise CommandError(f'Duplicate Team value on line {line_number}: {team}')
                seen_teams.add(team)

                objects.append(
                    MLBApiTeamDollarPerWar(
                        team=team,
                        avg_payroll_m_3yr=_to_float(raw.get('avg_payroll_M_3yr')),
                        avg_batting_war_3yr=_to_float(raw.get('avg_batting_war_3yr')),
                        avg_pitching_war_3yr=_to_float(raw.get('avg_pitching_war_3yr')),
                        avg_team_war_3yr=_to_float(raw.get('avg_team_war_3yr')),
                        n_years=_to_int(raw.get('n_years')),
                        avg_team_war_3yr_safe=_to_float(raw.get('avg_team_war_3yr_safe')),
                        dollar_per_war_millions=_to_float(raw.get('dollar_per_war_M')),
                        dollar_per_war=_to_float(raw.get('dollar_per_war')),
                    )
                )
        return objects
