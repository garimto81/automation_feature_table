#!/usr/bin/env python3
"""Metabase automatic setup script for PRD-0008 Monitoring Dashboard.

This script automates:
1. Initial admin user creation
2. PostgreSQL data source connection
3. Dashboard creation with 4 panels
4. Auto-refresh configuration

Usage:
    python setup_metabase.py [--host HOST] [--wait]

Environment Variables:
    METABASE_HOST: Metabase URL (default: http://localhost:3000)
    METABASE_ADMIN_EMAIL: Admin email (default: admin@poker.local)
    METABASE_ADMIN_PASSWORD: Admin password (required)
    DB_HOST: PostgreSQL host (default: db)
    DB_PORT: PostgreSQL port (default: 5432)
    DB_NAME: Database name (default: poker_hands)
    DB_USER: Database user (default: poker)
    DB_PASSWORD: Database password (required)
"""

import argparse
import os
import sys
import time

import requests

# Default configuration
DEFAULT_CONFIG = {
    "metabase_host": os.environ.get("METABASE_HOST", "http://localhost:3000"),
    "admin_email": os.environ.get("METABASE_ADMIN_EMAIL", "admin@poker.local"),
    "admin_password": os.environ.get("METABASE_ADMIN_PASSWORD", ""),
    "db_host": os.environ.get("DB_HOST", "db"),
    "db_port": int(os.environ.get("DB_PORT", "5432")),
    "db_name": os.environ.get("DB_NAME", "poker_hands"),
    "db_user": os.environ.get("DB_USER", "poker"),
    "db_password": os.environ.get("DB_PASSWORD", ""),
}


class MetabaseSetup:
    """Metabase setup automation."""

    def __init__(self, host: str):
        self.host = host.rstrip("/")
        self.session = requests.Session()
        self.session_token: str | None = None

    def wait_for_metabase(self, timeout: int = 120) -> bool:
        """Wait for Metabase to be ready."""
        print(f"Waiting for Metabase at {self.host}...")
        start = time.time()

        while time.time() - start < timeout:
            try:
                resp = self.session.get(f"{self.host}/api/health", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "ok":
                        print("Metabase is ready!")
                        return True
            except requests.RequestException:
                pass

            time.sleep(2)

        print(f"Timeout waiting for Metabase after {timeout}s")
        return False

    def check_setup_needed(self) -> bool:
        """Check if initial setup is needed."""
        try:
            resp = self.session.get(f"{self.host}/api/session/properties")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("setup-token") is not None
        except requests.RequestException as e:
            print(f"Error checking setup status: {e}")
        return False

    def initial_setup(
        self,
        admin_email: str,
        admin_password: str,
        site_name: str = "Poker Monitoring Dashboard",
    ) -> bool:
        """Perform initial Metabase setup."""
        print("Performing initial setup...")

        # Get setup token
        resp = self.session.get(f"{self.host}/api/session/properties")
        if resp.status_code != 200:
            print(f"Failed to get setup token: {resp.text}")
            return False

        setup_token = resp.json().get("setup-token")
        if not setup_token:
            print("No setup token found - setup may already be complete")
            return True

        # Perform setup
        setup_data = {
            "token": setup_token,
            "user": {
                "email": admin_email,
                "password": admin_password,
                "first_name": "Admin",
                "last_name": "User",
                "site_name": site_name,
            },
            "prefs": {
                "site_name": site_name,
                "site_locale": "ko",
                "allow_tracking": False,
            },
        }

        resp = self.session.post(f"{self.host}/api/setup", json=setup_data)
        if resp.status_code != 200:
            print(f"Setup failed: {resp.text}")
            return False

        # Save session token
        self.session_token = resp.json().get("id")
        if self.session_token:
            self.session.headers["X-Metabase-Session"] = self.session_token

        print("Initial setup complete!")
        return True

    def login(self, email: str, password: str) -> bool:
        """Login to Metabase."""
        print(f"Logging in as {email}...")

        resp = self.session.post(
            f"{self.host}/api/session",
            json={"username": email, "password": password},
        )

        if resp.status_code != 200:
            print(f"Login failed: {resp.text}")
            return False

        self.session_token = resp.json().get("id")
        if self.session_token:
            self.session.headers["X-Metabase-Session"] = self.session_token
            print("Login successful!")
            return True

        return False

    def add_database(
        self,
        name: str,
        host: str,
        port: int,
        db_name: str,
        user: str,
        password: str,
    ) -> int | None:
        """Add PostgreSQL database connection."""
        print(f"Adding database: {name}...")

        # Check if database already exists
        resp = self.session.get(f"{self.host}/api/database")
        if resp.status_code == 200:
            databases = resp.json()
            for db in databases.get("data", databases):
                if isinstance(db, dict) and db.get("name") == name:
                    print(f"Database '{name}' already exists (ID: {db['id']})")
                    return db["id"]

        # Add new database
        db_config = {
            "name": name,
            "engine": "postgres",
            "details": {
                "host": host,
                "port": port,
                "dbname": db_name,
                "user": user,
                "password": password,
                "ssl": False,
                "tunnel-enabled": False,
            },
            "auto_run_queries": True,
            "is_full_sync": True,
            "schedules": {},
        }

        resp = self.session.post(f"{self.host}/api/database", json=db_config)
        if resp.status_code not in (200, 201):
            print(f"Failed to add database: {resp.text}")
            return None

        db_id = resp.json().get("id")
        print(f"Database added with ID: {db_id}")
        return db_id

    def sync_database(self, db_id: int) -> bool:
        """Trigger database schema sync."""
        print(f"Syncing database schema (ID: {db_id})...")

        resp = self.session.post(f"{self.host}/api/database/{db_id}/sync_schema")
        if resp.status_code not in (200, 204):
            print(f"Sync failed: {resp.text}")
            return False

        print("Schema sync initiated!")
        return True

    def create_native_question(
        self,
        name: str,
        sql: str,
        db_id: int,
        display: str = "table",
        collection_id: int | None = None,
    ) -> int | None:
        """Create a native SQL question."""
        print(f"Creating question: {name}...")

        question_data = {
            "name": name,
            "dataset_query": {
                "database": db_id,
                "type": "native",
                "native": {"query": sql},
            },
            "display": display,
            "visualization_settings": {},
        }

        if collection_id:
            question_data["collection_id"] = collection_id

        resp = self.session.post(f"{self.host}/api/card", json=question_data)
        if resp.status_code not in (200, 201):
            print(f"Failed to create question: {resp.text}")
            return None

        card_id = resp.json().get("id")
        print(f"Question created with ID: {card_id}")
        return card_id

    def create_dashboard(
        self,
        name: str,
        description: str = "",
        collection_id: int | None = None,
    ) -> int | None:
        """Create a new dashboard."""
        print(f"Creating dashboard: {name}...")

        dashboard_data = {
            "name": name,
            "description": description,
        }

        if collection_id:
            dashboard_data["collection_id"] = collection_id

        resp = self.session.post(f"{self.host}/api/dashboard", json=dashboard_data)
        if resp.status_code not in (200, 201):
            print(f"Failed to create dashboard: {resp.text}")
            return None

        dashboard_id = resp.json().get("id")
        print(f"Dashboard created with ID: {dashboard_id}")
        return dashboard_id

    def add_card_to_dashboard(
        self,
        dashboard_id: int,
        card_id: int,
        row: int,
        col: int,
        size_x: int = 6,
        size_y: int = 4,
    ) -> bool:
        """Add a card (question) to a dashboard."""
        print(f"Adding card {card_id} to dashboard {dashboard_id}...")

        card_data = {
            "cardId": card_id,
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
        }

        resp = self.session.post(
            f"{self.host}/api/dashboard/{dashboard_id}/cards",
            json=card_data,
        )
        if resp.status_code not in (200, 201):
            print(f"Failed to add card: {resp.text}")
            return False

        print("Card added to dashboard!")
        return True

    def enable_auto_refresh(self, dashboard_id: int, interval_seconds: int = 5) -> bool:
        """Enable auto-refresh for dashboard."""
        print(f"Enabling auto-refresh ({interval_seconds}s) for dashboard {dashboard_id}...")

        # Note: Auto-refresh is typically a client-side setting
        # This sets the default refresh interval in dashboard parameters
        resp = self.session.put(
            f"{self.host}/api/dashboard/{dashboard_id}",
            json={"cache_ttl": interval_seconds},
        )

        if resp.status_code not in (200, 204):
            print(f"Failed to set refresh: {resp.text}")
            return False

        print("Auto-refresh configured!")
        return True


# SQL queries for dashboard cards
DASHBOARD_QUERIES = {
    "table_status": {
        "name": "Table Status Overview",
        "display": "table",
        "sql": """
SELECT
    table_id AS "테이블",
    CASE WHEN primary_connected THEN '● ON' ELSE '○ OFF' END AS "Primary",
    CASE WHEN secondary_connected THEN '● ON' ELSE '○ OFF' END AS "Secondary",
    current_hand_number AS "현재 핸드",
    CASE
        WHEN hand_start_time IS NULL THEN '-'
        ELSE TO_CHAR(NOW() - hand_start_time, 'MI:SS')
    END AS "진행 시간",
    COALESCE(last_fusion_result, '-') AS "Fusion 상태"
FROM table_status
ORDER BY table_id
""",
    },
    "grade_distribution": {
        "name": "Hand Grade Distribution",
        "display": "pie",
        "sql": """
SELECT
    g.grade AS "등급",
    COUNT(*) AS "핸드 수"
FROM grades g
JOIN hands h ON g.hand_id = h.id
WHERE h.started_at >= CURRENT_DATE
GROUP BY g.grade
ORDER BY g.grade
""",
    },
    "recording_sessions": {
        "name": "Active Recording Sessions",
        "display": "table",
        "sql": """
SELECT
    session_id AS "세션 ID",
    table_id AS "테이블",
    CASE status
        WHEN 'recording' THEN '● REC'
        WHEN 'stopped' THEN '○ 정지'
        WHEN 'completed' THEN '✓ 완료'
        ELSE status
    END AS "상태",
    TO_CHAR(NOW() - start_time, 'HH24:MI:SS') AS "녹화 시간",
    COALESCE(ROUND(file_size_mb / 1024.0, 2) || ' GB', '-') AS "파일 크기"
FROM recording_sessions
WHERE status = 'recording' OR end_time >= NOW() - INTERVAL '1 hour'
ORDER BY start_time DESC
LIMIT 10
""",
    },
    "system_health": {
        "name": "System Health Status",
        "display": "table",
        "sql": """
SELECT
    service_name AS "서비스",
    CASE status
        WHEN 'connected' THEN '● 연결됨'
        WHEN 'disconnected' THEN '○ 끊김'
        WHEN 'error' THEN '✗ 오류'
        WHEN 'warning' THEN '⚠ 경고'
        ELSE status
    END AS "상태",
    COALESCE(latency_ms || 'ms', '-') AS "지연",
    TO_CHAR(created_at, 'HH24:MI:SS') AS "체크 시간"
FROM system_health_log l1
WHERE created_at = (
    SELECT MAX(created_at)
    FROM system_health_log l2
    WHERE l2.service_name = l1.service_name
)
ORDER BY service_name
""",
    },
}


def main() -> int:
    """Main setup function."""
    parser = argparse.ArgumentParser(description="Metabase automatic setup")
    parser.add_argument(
        "--host",
        default=DEFAULT_CONFIG["metabase_host"],
        help="Metabase host URL",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for Metabase to be ready",
    )
    args = parser.parse_args()

    # Validate required config
    if not DEFAULT_CONFIG["admin_password"]:
        print("Error: METABASE_ADMIN_PASSWORD environment variable is required")
        return 1

    if not DEFAULT_CONFIG["db_password"]:
        print("Error: DB_PASSWORD environment variable is required")
        return 1

    setup = MetabaseSetup(args.host)

    # Wait for Metabase if requested
    if args.wait:
        if not setup.wait_for_metabase():
            return 1

    # Check if initial setup is needed
    if setup.check_setup_needed():
        if not setup.initial_setup(
            DEFAULT_CONFIG["admin_email"],
            DEFAULT_CONFIG["admin_password"],
        ):
            print("Initial setup failed")
            return 1
    else:
        # Login with existing credentials
        if not setup.login(
            DEFAULT_CONFIG["admin_email"],
            DEFAULT_CONFIG["admin_password"],
        ):
            print("Login failed")
            return 1

    # Add PostgreSQL database
    db_id = setup.add_database(
        name="Poker Hands DB",
        host=DEFAULT_CONFIG["db_host"],
        port=DEFAULT_CONFIG["db_port"],
        db_name=DEFAULT_CONFIG["db_name"],
        user=DEFAULT_CONFIG["db_user"],
        password=DEFAULT_CONFIG["db_password"],
    )

    if not db_id:
        print("Failed to add database")
        return 1

    # Sync schema
    setup.sync_database(db_id)

    # Wait a bit for schema sync
    print("Waiting for schema sync...")
    time.sleep(5)

    # Create dashboard
    dashboard_id = setup.create_dashboard(
        name="Poker Monitoring Dashboard",
        description="Real-time monitoring for poker hand capture system (PRD-0008)",
    )

    if not dashboard_id:
        print("Failed to create dashboard")
        return 1

    # Create questions and add to dashboard
    card_positions = [
        ("table_status", 0, 0, 6, 4),
        ("grade_distribution", 6, 0, 6, 4),
        ("recording_sessions", 0, 4, 6, 4),
        ("system_health", 6, 4, 6, 4),
    ]

    for query_key, col, row, size_x, size_y in card_positions:
        query = DASHBOARD_QUERIES[query_key]
        card_id = setup.create_native_question(
            name=query["name"],
            sql=query["sql"],
            db_id=db_id,
            display=query["display"],
        )

        if card_id:
            setup.add_card_to_dashboard(
                dashboard_id=dashboard_id,
                card_id=card_id,
                row=row,
                col=col,
                size_x=size_x,
                size_y=size_y,
            )

    # Enable auto-refresh
    setup.enable_auto_refresh(dashboard_id, interval_seconds=5)

    print("\n" + "=" * 60)
    print("Setup complete!")
    print(f"Dashboard URL: {args.host}/dashboard/{dashboard_id}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
