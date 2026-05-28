import time
import requests

from django.core.management.base import BaseCommand
from django.db import transaction

from mlb.models import MLBApiStatLine


PEOPLE_URL = 'https://statsapi.mlb.com/api/v1/people'
BATCH_SIZE = 100
REQUEST_DELAY = 0.3


class Command(BaseCommand):
    help = 'Enrich MLBApiStatLine.raw_stats with bio fields from MLB StatsAPI (height, weight, position, bats, throws, debut_year).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update even if bio fields are already present.',
        )

    def handle(self, *args, **options):
        force = options['force']

        qs = MLBApiStatLine.objects.exclude(mlbam_id='').exclude(mlbam_id__isnull=True)
        all_lines = list(qs)
        if not force:
            all_lines = [l for l in all_lines if not (l.raw_stats or {}).get('Height')]

        if not all_lines:
            self.stdout.write('No stat lines need enrichment.')
            return

        # Collect distinct mlbam_ids → map to stat lines
        id_to_lines = {}
        for line in all_lines:
            mid = str(line.mlbam_id).strip()
            if mid:
                id_to_lines.setdefault(mid, []).append(line)

        mlbam_ids = list(id_to_lines.keys())
        self.stdout.write(f'Fetching bios for {len(mlbam_ids)} distinct players across {len(all_lines)} stat lines...')

        bio_map = {}
        for i in range(0, len(mlbam_ids), BATCH_SIZE):
            batch = mlbam_ids[i:i + BATCH_SIZE]
            try:
                resp = requests.get(PEOPLE_URL, params={'personIds': ','.join(batch)}, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.stdout.write(self.style.WARNING(f'Request failed for batch {i//BATCH_SIZE + 1}: {exc}'))
                continue

            for person in resp.json().get('people', []):
                pid = str(person.get('id', ''))
                if not pid:
                    continue
                debut_raw = person.get('mlbDebutDate') or ''
                bio_map[pid] = {
                    'Height': person.get('height') or '',
                    'Weight': str(person.get('weight') or ''),
                    'Position': person.get('primaryPosition', {}).get('abbreviation') or '',
                    'Bats': person.get('batSide', {}).get('code') or '',
                    'Throws': person.get('pitchHand', {}).get('code') or '',
                    'DebutYear': debut_raw[:4] if debut_raw else '',
                }

            self.stdout.write(f'  Batch {i//BATCH_SIZE + 1}/{(len(mlbam_ids) - 1)//BATCH_SIZE + 1} done.')
            time.sleep(REQUEST_DELAY)

        updated_lines = []
        for mid, lines in id_to_lines.items():
            bio = bio_map.get(mid)
            if not bio:
                continue
            for line in lines:
                raw = dict(line.raw_stats or {})
                for key, val in bio.items():
                    if val:
                        raw[key] = val
                line.raw_stats = raw
                updated_lines.append(line)

        with transaction.atomic():
            MLBApiStatLine.objects.bulk_update(updated_lines, ['raw_stats'], batch_size=500)

        self.stdout.write(self.style.SUCCESS(f'Enriched {len(updated_lines)} stat lines with bio data.'))
