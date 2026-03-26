import mimetypes
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from mlb.models import MLBRosterPhoto


SUPPORTED_EXTENSIONS = {'.jpeg', '.jpg', '.png', '.webp'}


def _normalize_player_name(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch.lower() for ch in ascii_only if ch.isalnum())


class Command(BaseCommand):
    help = 'Load roster player photos from data/<Team Name>/ folders into the DB.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing MLBRosterPhoto rows before loading.',
        )
        parser.add_argument(
            '--base-dir',
            default=str(settings.BASE_DIR),
            help='Project base directory containing the data/ folder.',
        )

    def handle(self, *args, **options):
        if options['replace']:
            deleted_count, _ = MLBRosterPhoto.objects.all().delete()
            self.stdout.write(f'Deleted {deleted_count} existing roster photo rows.')

        data_dir = Path(options['base_dir']) / 'data'
        if not data_dir.exists():
            self.stderr.write(self.style.WARNING(f'Data directory not found: {data_dir}'))
            return

        total_upserts = 0
        for team_dir in sorted(path for path in data_dir.iterdir() if path.is_dir()):
            for image_path in sorted(team_dir.iterdir()):
                if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                player_name = image_path.stem.strip()
                normalized_player_name = _normalize_player_name(player_name)
                if not normalized_player_name:
                    continue

                content_type, _ = mimetypes.guess_type(image_path.name)
                image_data = image_path.read_bytes()
                MLBRosterPhoto.objects.update_or_create(
                    team_name=team_dir.name,
                    normalized_player_name=normalized_player_name,
                    defaults={
                        'player_name': player_name,
                        'original_filename': image_path.name,
                        'content_type': content_type or 'application/octet-stream',
                        'image_data': image_data,
                        'byte_size': len(image_data),
                    },
                )
                total_upserts += 1

        self.stdout.write(self.style.SUCCESS(f'Loaded or updated {total_upserts} roster photo rows.'))
