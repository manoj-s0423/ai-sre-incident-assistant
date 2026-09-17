import sqlite3
import json
from datetime import datetime


DATABASE = "incidents.db"


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# Database Initialization
# ============================================================

def init_db():

    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE,
            alert_name TEXT NOT NULL,
            service TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            resolved_at TEXT,
            incident_summary TEXT,
            root_cause TEXT,
            root_cause_identified INTEGER DEFAULT 0,
            affected_component TEXT,
            impact TEXT,
            confidence TEXT,
            conclusion TEXT,
            evidence TEXT,
            recommended_actions TEXT,
            additional_evidence_needed TEXT,
            investigation TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # ========================================================
    # Database Migration
    # ========================================================

    columns = conn.execute("""
        PRAGMA table_info(incidents)
    """).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    # --------------------------------------------------------
    # Add investigation column
    # --------------------------------------------------------

    if "investigation" not in column_names:

        conn.execute("""
            ALTER TABLE incidents
            ADD COLUMN investigation TEXT
        """)

    # --------------------------------------------------------
    # Add root_cause_identified column
    # --------------------------------------------------------

    if "root_cause_identified" not in column_names:

        conn.execute("""
            ALTER TABLE incidents
            ADD COLUMN root_cause_identified INTEGER
            DEFAULT 0
        """)

    # --------------------------------------------------------
    # Add conclusion column
    # --------------------------------------------------------

    if "conclusion" not in column_names:

        conn.execute("""
            ALTER TABLE incidents
            ADD COLUMN conclusion TEXT
        """)

    conn.commit()
    conn.close()
# ============================================================
# Create Incident
# ============================================================

def create_incident(
    fingerprint,
    alert_name,
    service,
    severity,
    started_at
):

    conn = get_connection()

    now = datetime.utcnow().isoformat()

    # ========================================================
    # Check if Incident Already Exists
    # ========================================================

    existing = conn.execute("""
        SELECT id
        FROM incidents
        WHERE fingerprint = ?
    """, (
        fingerprint,
    )).fetchone()

    # ========================================================
    # Existing Incident
    # ========================================================

    if existing:

        conn.execute("""
            UPDATE incidents
            SET
                alert_name = ?,
                service = ?,
                severity = ?,
                updated_at = ?
            WHERE fingerprint = ?
        """, (
            alert_name,
            service,
            severity,
            now,
            fingerprint
        ))

        conn.commit()
        conn.close()

        return existing["id"]

    # ========================================================
    # New Incident
    # ========================================================

    cursor = conn.execute("""
        INSERT INTO incidents (
            fingerprint,
            alert_name,
            service,
            severity,
            status,
            started_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        fingerprint,
        alert_name,
        service,
        severity,
        "investigating",
        started_at,
        now,
        now
    ))

    conn.commit()

    incident_id = cursor.lastrowid

    conn.close()

    return incident_id


# ============================================================
# Update Incident
# ============================================================

def update_incident(
    fingerprint,
    rca
):

    conn = get_connection()

    now = datetime.utcnow().isoformat()

    # ========================================================
    # Extract Investigation
    # ========================================================

    investigation_steps = rca.get(
        "investigation_steps"
    )

    if investigation_steps is None:

        investigation_steps = rca.get(
            "steps"
        )

    if investigation_steps is None:

        investigation_steps = []

    # ========================================================
    # Root Cause Status
    # ========================================================

    root_cause_identified = rca.get(
        "root_cause_identified",
        False
    )

    # SQLite stores boolean values as INTEGER.

    root_cause_identified = int(
        bool(root_cause_identified)
    )

    # ========================================================
    # Update Database
    # ========================================================

    conn.execute("""
        UPDATE incidents
        SET
            status = ?,
            incident_summary = ?,
            root_cause = ?,
            root_cause_identified = ?,
            affected_component = ?,
            impact = ?,
            confidence = ?,
            conclusion = ?,
            evidence = ?,
            recommended_actions = ?,
            additional_evidence_needed = ?,
            investigation = ?,
            updated_at = ?
        WHERE fingerprint = ?
    """, (

        rca.get(
            "status",
            "investigated"
        ),

        rca.get(
            "incident_summary"
        ),

        rca.get(
            "root_cause"
        ),

        root_cause_identified,

        rca.get(
            "affected_component"
        ),

        rca.get(
            "impact"
        ),

        rca.get(
            "confidence"
        ),

        rca.get(
            "conclusion"
        ),

        json.dumps(
            rca.get(
                "evidence",
                []
            ),
            default=str
        ),

        json.dumps(
            rca.get(
                "recommended_actions",
                []
            ),
            default=str
        ),

        json.dumps(
            rca.get(
                "additional_evidence_needed",
                []
            ),
            default=str
        ),

        json.dumps(
            investigation_steps,
            default=str
        ),

        now,

        fingerprint
    ))

    conn.commit()
    conn.close()

# ============================================================
# Resolve Incident
# ============================================================

def resolve_incident(
    fingerprint,
    resolved_at
):

    conn = get_connection()

    now = datetime.utcnow().isoformat()

    conn.execute("""
        UPDATE incidents
        SET
            status = ?,
            resolved_at = ?,
            updated_at = ?
        WHERE fingerprint = ?
    """, (
        "resolved",
        resolved_at,
        now,
        fingerprint
    ))

    conn.commit()
    conn.close()


# ============================================================
# Get All Incidents
# ============================================================

def get_incidents():

    conn = get_connection()

    rows = conn.execute("""
        SELECT *
        FROM incidents
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# Get Incident By ID
# ============================================================

def get_incident_by_id(
    incident_id
):

    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM incidents
        WHERE id = ?
    """, (
        incident_id,
    )).fetchone()

    conn.close()

    if row:
        return dict(row)

    return None


# ============================================================
# Get Incident By Fingerprint
# ============================================================

def get_incident_by_fingerprint(
    fingerprint
):

    conn = get_connection()

    row = conn.execute("""
        SELECT *
        FROM incidents
        WHERE fingerprint = ?
    """, (
        fingerprint,
    )).fetchone()

    conn.close()

    if row:
        return dict(row)

    return None


# ============================================================
# MTTR Calculation
# ============================================================

def calculate_mttr():

    conn = get_connection()

    rows = conn.execute("""
        SELECT
            started_at,
            resolved_at
        FROM incidents
        WHERE status = 'resolved'
        AND started_at IS NOT NULL
        AND resolved_at IS NOT NULL
    """).fetchall()

    conn.close()

    if not rows:
        return 0

    durations = []

    for row in rows:

        try:

            start = datetime.fromisoformat(
                row["started_at"].replace(
                    "Z",
                    "+00:00"
                )
            )

            end = datetime.fromisoformat(
                row["resolved_at"].replace(
                    "Z",
                    "+00:00"
                )
            )

            # =================================================
            # Handle timezone-naive and timezone-aware values
            # =================================================

            if (
                start.tzinfo is None
                and end.tzinfo is not None
            ):

                end = end.replace(
                    tzinfo=None
                )

            elif (
                start.tzinfo is not None
                and end.tzinfo is None
            ):

                start = start.replace(
                    tzinfo=None
                )

            duration = (
                end - start
            ).total_seconds()

            if duration >= 0:

                durations.append(
                    duration
                )

        except (
            ValueError,
            TypeError
        ):

            continue

    if not durations:
        return 0

    return (
        sum(durations)
        / len(durations)
    )


# ============================================================
# Incident Statistics
# ============================================================

def get_incident_stats():

    conn = get_connection()

    total = conn.execute("""
        SELECT COUNT(*) AS count
        FROM incidents
    """).fetchone()["count"]

    resolved = conn.execute("""
        SELECT COUNT(*) AS count
        FROM incidents
        WHERE status = 'resolved'
    """).fetchone()["count"]

    active = conn.execute("""
        SELECT COUNT(*) AS count
        FROM incidents
        WHERE status != 'resolved'
    """).fetchone()["count"]

    conn.close()

    return {
        "total": total,
        "resolved": resolved,
        "active": active,
        "mttr_seconds": calculate_mttr()
    }


# ============================================================
# Incidents By Severity
# ============================================================

def get_incidents_by_severity():

    conn = get_connection()

    rows = conn.execute("""
        SELECT
            severity,
            COUNT(*) AS count
        FROM incidents
        GROUP BY severity
        ORDER BY count DESC
    """).fetchall()

    conn.close()

    return [
        {
            "severity": row["severity"],
            "count": row["count"]
        }
        for row in rows
    ]


# ============================================================
# Incidents By Service
# ============================================================

def get_incidents_by_service():

    conn = get_connection()

    rows = conn.execute("""
        SELECT
            service,
            COUNT(*) AS count
        FROM incidents
        GROUP BY service
        ORDER BY count DESC
    """).fetchall()

    conn.close()

    return [
        {
            "service": row["service"],
            "count": row["count"]
        }
        for row in rows
    ]


# ============================================================
# Incident Trends
# ============================================================

def get_incident_trends():

    conn = get_connection()

    rows = conn.execute("""
        SELECT
            DATE(created_at) AS date,
            COUNT(*) AS count
        FROM incidents
        GROUP BY DATE(created_at)
        ORDER BY date
    """).fetchall()

    conn.close()

    return [
        {
            "date": row["date"],
            "count": row["count"]
        }
        for row in rows
    ]


# ============================================================
# Resolution Rate
# ============================================================

def get_resolution_rate():

    conn = get_connection()

    total = conn.execute("""
        SELECT COUNT(*) AS count
        FROM incidents
    """).fetchone()["count"]

    resolved = conn.execute("""
        SELECT COUNT(*) AS count
        FROM incidents
        WHERE status = 'resolved'
    """).fetchone()["count"]

    conn.close()

    if total == 0:
        return 0

    return (
        resolved / total
    ) * 100


# ============================================================
# Recurring Incidents
# ============================================================

def get_recurring_incidents():

    conn = get_connection()

    rows = conn.execute("""
        SELECT
            alert_name,
            service,
            COUNT(*) AS count
        FROM incidents
        GROUP BY alert_name, service
        ORDER BY count DESC
    """).fetchall()

    conn.close()

    return [
        {
            "alert_name": row["alert_name"],
            "service": row["service"],
            "count": row["count"]
        }
        for row in rows
    ]


# ============================================================
# MTTR Trends
# ============================================================

def get_mttr_trends():

    conn = get_connection()

    rows = conn.execute("""
        SELECT
            DATE(started_at) AS date,
            started_at,
            resolved_at
        FROM incidents
        WHERE status = 'resolved'
        AND started_at IS NOT NULL
        AND resolved_at IS NOT NULL
        ORDER BY started_at
    """).fetchall()

    conn.close()

    daily_mttr = {}

    for row in rows:

        try:

            start = datetime.fromisoformat(
                row["started_at"].replace(
                    "Z",
                    "+00:00"
                )
            )

            end = datetime.fromisoformat(
                row["resolved_at"].replace(
                    "Z",
                    "+00:00"
                )
            )

            if (
                start.tzinfo is None
                and end.tzinfo is not None
            ):

                end = end.replace(
                    tzinfo=None
                )

            elif (
                start.tzinfo is not None
                and end.tzinfo is None
            ):

                start = start.replace(
                    tzinfo=None
                )

            duration_seconds = (
                end - start
            ).total_seconds()

            if duration_seconds < 0:
                continue

            date = row["date"]

            if date not in daily_mttr:

                daily_mttr[date] = []

            daily_mttr[date].append(
                duration_seconds
            )

        except (
            ValueError,
            TypeError
        ):

            continue

    result = []

    for date, durations in daily_mttr.items():

        if not durations:
            continue

        average_seconds = (
            sum(durations)
            / len(durations)
        )

        result.append({
            "date": date,
            "mttr_seconds": round(
                average_seconds,
                2
            ),
            "mttr_minutes": round(
                average_seconds / 60,
                2
            )
        })

    return result