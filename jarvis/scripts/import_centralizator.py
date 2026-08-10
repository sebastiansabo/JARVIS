"""CLI for the CarPark Dispo centralizator XLSX importer (Phase 5, Task 5.2).

Migrates the backoffice's `centralizator AAP.xlsx` (sheet AUDI) into
carpark_vehicles + cost/revenue rows. Defaults to a DRY RUN (parses and
validates, prints a report, writes nothing) — pass --commit to actually
upsert into the DB.

Usage:
    DATABASE_URL=postgresql://localhost/defaultdb \
        python scripts/import_centralizator.py --file "centralizator AAP.xlsx" --company-id 1

    # actually write:
    DATABASE_URL=postgresql://localhost/defaultdb \
        python scripts/import_centralizator.py --file "centralizator AAP.xlsx" --company-id 1 --commit
"""
import argparse
import os
import sys

# Make `jarvis/` importable regardless of the caller's cwd (this file lives
# at jarvis/scripts/import_centralizator.py; jarvis/ itself has no
# __init__.py and isn't a package, mirroring how the test suite resolves
# `from carpark... import ...` / `from database import ...`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from carpark.services.import_service import CentralizatorImporter  # noqa: E402


def _print_report(report, max_problems: int) -> None:
    mode = 'DRY RUN' if report.dry_run else 'COMMIT'
    print(f'== Centralizator import — {mode} (company_id={report.company_id}) ==')
    print(f'  total rows:          {report.total}')
    print(f'  ok:                  {report.ok}  (of which with warnings: {report.warnings})')
    print(f'  skipped (no VIN):    {report.skipped_no_vin}')
    print(f'  rejected:            {report.rejects}')
    print(f'  cross-company:       {report.cross_company}  (VIN owned by another company — never written)')

    if not report.dry_run:
        print(f'  vehicles created:    {report.committed_vehicles_created}')
        print(f'  vehicles updated:    {report.committed_vehicles_updated}')
        print(f'  cost rows written:   {report.committed_cost_rows}')
        print(f'  revenue rows written:{report.committed_revenue_rows}')

    if report.error:
        print(f'\n  !! COMMIT FAILED, rolled back: {report.error}')

    problems = [r for r in report.rows if r['status'] != 'ok' or r['warnings']]
    if problems:
        print(f'\n  problem rows ({len(problems)} total, showing up to {max_problems}):')
        for r in problems[:max_problems]:
            reason = r.get('reject_reason') or '; '.join(r['warnings']) or r['status']
            print(f"    sheet={r['sheet']:<10} row={r['row']:<4} vin={r['vin'] or '(none)':<20} "
                  f"status={r['status']:<16} {reason}")
        if len(problems) > max_problems:
            print(f'    ... and {len(problems) - max_problems} more')

    if report.unmatched_names:
        print(f'\n  unmatched Vanzator/Achizitor names ({len(report.unmatched_names)}):')
        for n in report.unmatched_names:
            print(f'    - {n}')


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Import the centralizator AAP.xlsx sales tracker into carpark_vehicles')
    parser.add_argument('--file', required=True, help='Path to the .xlsx file')
    parser.add_argument('--company-id', type=int, required=True,
                         help='carpark_vehicles.company_id to import new vehicles into')
    parser.add_argument('--commit', action='store_true',
                         help='Actually write to the DB (default: dry run, no writes)')
    parser.add_argument('--max-problems', type=int, default=25,
                         help='Max problem rows to print in the report (default: 25)')
    args = parser.parse_args()

    importer = CentralizatorImporter()
    try:
        report = importer.run(args.file, args.company_id, dry_run=not args.commit)
    except ValueError as e:
        print(f'Import failed: {e}', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'Import failed (commit rolled back): {e}', file=sys.stderr)
        return 1

    _print_report(report, args.max_problems)
    return 0


if __name__ == '__main__':
    sys.exit(main())
