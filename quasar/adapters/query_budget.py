"""Read BigQuery job metadata to reserve monthly scan allowance; no table scan."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CEILING = 1_000_000_000_000


def reservation(job):
    query = job.get('configuration', {}).get('query')
    if not isinstance(query, dict):
        return 0
    stats = job.get('statistics', {}).get('query', {})
    if job.get('status', {}).get('state') != 'DONE':
        return int(query.get('maximumBytesBilled', CEILING + 1))
    return int(stats.get('totalBytesBilled', stats.get('totalBytesProcessed', 0)))


def audit(project, location='US', *, now=None):
    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    base = ['bq', f'--project_id={project}', f'--location={location}', '--format=json']
    def read(command):
        return json.loads(subprocess.run(command, check=True, text=True, capture_output=True, timeout=120).stdout)
    jobs = read(base + ['ls', '-j', '-a', '--max_results=1000'])
    if not isinstance(jobs, list) or len(jobs) >= 1000:
        raise ValueError('Job inventory may be truncated; monthly allowance is unknown')
    records = []
    for item in jobs:
        created = item.get('statistics', {}).get('creationTime')
        if created is None:
            raise ValueError('Job creation time missing; monthly allowance is unknown')
        if int(created) < start:
            continue
        job_id = item['jobReference']['jobId']
        job = read(base + ['show', '-j', job_id])
        if 'query' not in job.get('configuration', {}):
            continue
        records.append({'job_id': job_id, 'state': job['status']['state'],
                        'bytes_reserved_or_billed': reservation(job),
                        'bytes_processed': job.get('statistics', {}).get('query', {}).get('totalBytesProcessed')})
    total = sum(row['bytes_reserved_or_billed'] for row in records)
    return {'project': project, 'location': location, 'month_utc': now.strftime('%Y-%m'),
            'checked_at': now.isoformat(), 'bytes_reserved_or_billed': total,
            'conservative_ceiling': CEILING, 'remaining_planning_bytes': max(0, CEILING - total), 'jobs': records}


def main():
    from .historical import write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--location', default='US')
    parser.add_argument('--output', type=Path, default=Path('data/processed/okaloosa/weathernext-budget.json'))
    args = parser.parse_args()
    report = audit(args.project, args.location)
    write_json(args.output, report)
    print(json.dumps({k:v for k,v in report.items() if k!='jobs'}, indent=2))


if __name__ == '__main__':
    main()
