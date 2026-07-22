"""
Automated PostgreSQL Backup — Exports critical tables to JSON daily.

Since Railway doesn't support pg_dump via cron easily, this script
exports signal_history and live_trades to JSON files that persist in
the output/ directory AND can be committed to git as a safety net.

Usage:
    python scripts/backup_db.py          # Manual run
    Called by: /api/live/run-backup       # API endpoint (future)

Backs up:
    - signal_history (all signals ever generated)
    - live_trades (all paper/live trades with P&L)
    - users (account data)
    - upload_history (DNA uploads)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.database import get_connection


def run_backup():
    """Export critical tables to JSON backup files."""
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    conn = get_connection()
    
    tables = ["signal_history", "live_trades", "users", "upload_history"]
    backup_data = {}
    
    try:
        for table in tables:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                backup_data[table] = [dict(r) for r in rows] if rows else []
                print(f"  {table}: {len(backup_data[table])} rows")
            except Exception as e:
                print(f"  {table}: SKIP ({e})")
                backup_data[table] = []
        
        # Save combined backup
        backup_path = backup_dir / f"backup_{timestamp}.json"
        with open(backup_path, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        # Also save a "latest" copy (always overwritten)
        latest_path = backup_dir / "latest_backup.json"
        with open(latest_path, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        total_rows = sum(len(v) for v in backup_data.values())
        print(f"\n✅ Backup saved: {backup_path.name} ({total_rows} total rows)")
        print(f"   Latest copy: {latest_path.name}")
        
        return {
            "success": True,
            "file": str(backup_path.name),
            "rows": total_rows,
            "tables": {k: len(v) for k, v in backup_data.items()},
        }
    
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 50)
    print("OPTIONS TYCOON — Database Backup")
    print("=" * 50)
    run_backup()
