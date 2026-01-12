"""Sync NAS JSON files to Supabase."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.config.settings import get_settings
from src.database.supabase_client import SupabaseManager
from src.database.supabase_repository import GFXSessionRepository, SyncLogRepository


async def sync_nas(nas_path_str: str) -> None:
    """Sync all JSON files from NAS to Supabase."""
    settings = get_settings()
    supabase = SupabaseManager(settings.supabase)
    session_repo = GFXSessionRepository(supabase)
    sync_log_repo = SyncLogRepository(supabase)

    nas_path = Path(nas_path_str)

    print(f"NAS Path: {nas_path}")
    print("=" * 60)

    # List files
    try:
        files = os.listdir(nas_path_str)
        print(f"Files in directory: {files}")
        json_files = [nas_path / f for f in files if f.endswith(".json")]
        print(f"Found {len(json_files)} JSON files")
    except Exception as e:
        print(f"Error listing directory: {e}")
        return

    print()

    synced = 0
    skipped = 0

    for test_file in json_files:
        print(f"Processing: {test_file.name}")

        with open(test_file, encoding="utf-8") as f:
            content = f.read()

        data = json.loads(content)
        file_hash = SupabaseManager.compute_file_hash(content.encode("utf-8"))

        # Check if already processed
        if await sync_log_repo.is_file_processed(file_hash):
            print("  -> Skipped (already processed)")
            skipped += 1
            continue

        # Log and save
        sync_log = await sync_log_repo.log_sync_start(
            file_name=test_file.name,
            file_path=str(test_file),
            file_hash=file_hash,
            file_size_bytes=test_file.stat().st_size,
            operation="created",
        )

        # Extract session ID from filename if not in JSON
        # Filename format: PGFX_live_data_export GameID=638963849867159576.json
        session_id = data.get("ID")
        if session_id is None:
            import re
            match = re.search(r"GameID=(\d+)", test_file.name)
            session_id = int(match.group(1)) if match else 0
            # Add ID to raw_json for consistency
            data["ID"] = session_id

        # Add Type if not present (default to FEATURE_TABLE)
        if "Type" not in data:
            data["Type"] = "FEATURE_TABLE"

        hand_count = len(data.get("Hands", []))
        table_type = data.get("Type")

        session_record = await session_repo.save_session(
            session_id=session_id,
            file_name=test_file.name,
            file_hash=file_hash,
            raw_json=data,
            nas_path=str(test_file),
        )

        if session_record:
            await sync_log_repo.log_sync_complete(
                log_id=sync_log["id"],
                session_id=session_record["id"],
                status="success",
            )
            print("  -> Synced!")
            print(f"     Session ID: {session_id}")
            print(f"     Type: {table_type}")
            print(f"     Hands: {hand_count}")
            synced += 1
        else:
            await sync_log_repo.log_sync_complete(
                log_id=sync_log["id"],
                status="skipped",
                error_message="Duplicate session",
            )
            print("  -> Skipped (duplicate)")
            skipped += 1

    print()
    print("=" * 60)
    print(f"Results: {synced} synced, {skipped} skipped")

    # Show all sessions
    sessions = await session_repo.list_recent_sessions(limit=10)
    print(f"\nTotal sessions in Supabase: {len(sessions)}")
    for s in sessions:
        print(f'  [{s["table_type"]}] Session {s["session_id"]}: {s["hand_count"]} hands')


if __name__ == "__main__":
    # Default NAS path
    nas_path = sys.argv[1] if len(sys.argv) > 1 else r"Z:\pokergfx\hands"
    asyncio.run(sync_nas(nas_path))
