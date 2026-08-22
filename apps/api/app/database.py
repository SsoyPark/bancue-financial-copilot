import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .models import (
    ActionRecord,
    Consultation,
    ConsultationStatus,
    FeedbackRecord,
    FeedbackSummary,
)


class WorkflowStateStore:
    """상담 상태·처리 이력과 마스킹된 품질 피드백을 SQLite에 저장한다."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_state (
                    consultation_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    restriction_reason TEXT,
                    action_history_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS consultation_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    consultation_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    intent_score INTEGER NOT NULL DEFAULT 0,
                    draft_score INTEGER NOT NULL DEFAULT 0,
                    issue_types_json TEXT NOT NULL,
                    note TEXT,
                    pii_masked INTEGER NOT NULL,
                    pii_types_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            feedback_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(consultation_feedback)"
                ).fetchall()
            }
            if "intent_score" not in feedback_columns:
                connection.execute(
                    "ALTER TABLE consultation_feedback "
                    "ADD COLUMN intent_score INTEGER NOT NULL DEFAULT 0"
                )
            if "draft_score" not in feedback_columns:
                connection.execute(
                    "ALTER TABLE consultation_feedback "
                    "ADD COLUMN draft_score INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feedback_consultation
                ON consultation_feedback (consultation_id)
                """
            )

    def save(self, consultation: Consultation) -> None:
        action_history_json = json.dumps(
            [record.model_dump(mode="json") for record in consultation.action_history],
            ensure_ascii=False,
        )
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_state (
                    consultation_id,
                    status,
                    restriction_reason,
                    action_history_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(consultation_id) DO UPDATE SET
                    status = excluded.status,
                    restriction_reason = excluded.restriction_reason,
                    action_history_json = excluded.action_history_json,
                    updated_at = excluded.updated_at
                """,
                (
                    consultation.id,
                    consultation.status.value,
                    consultation.restriction_reason,
                    action_history_json,
                    updated_at,
                ),
            )

    def restore(self, consultation: Consultation) -> Consultation:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status, restriction_reason, action_history_json
                FROM workflow_state
                WHERE consultation_id = ?
                """,
                (consultation.id,),
            ).fetchone()

        if row is None:
            return consultation

        try:
            status = ConsultationStatus(row["status"])
            history_payload = json.loads(row["action_history_json"])
            action_history = [
                ActionRecord.model_validate(record) for record in history_payload
            ]
        except (ValueError, TypeError, json.JSONDecodeError):
            return consultation

        return consultation.model_copy(
            update={
                "status": status,
                "restriction_reason": row["restriction_reason"],
                "action_history": action_history,
            }
        )

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM workflow_state"
            ).fetchone()
        return int(row["count"] if row else 0)

    def save_feedback(self, feedback: FeedbackRecord) -> FeedbackRecord:
        """개인정보가 마스킹된 상담사 피드백을 추가한다."""
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO consultation_feedback (
                    consultation_id,
                    rating,
                    intent_score,
                    draft_score,
                    issue_types_json,
                    note,
                    pii_masked,
                    pii_types_json,
                    actor,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.consultation_id,
                    feedback.rating.value,
                    feedback.intent_score,
                    feedback.draft_score,
                    json.dumps(
                        [issue.value for issue in feedback.issue_types],
                        ensure_ascii=False,
                    ),
                    feedback.note,
                    int(feedback.pii_masked),
                    json.dumps(feedback.pii_types, ensure_ascii=False),
                    feedback.actor,
                    feedback.created_at,
                ),
            )
            feedback_id = int(cursor.lastrowid)
        return feedback.model_copy(update={"id": feedback_id})

    def feedback_summary(self, recent_limit: int = 20) -> FeedbackSummary:
        """피드백 비율, 개선 유형과 최근 기록을 집계한다."""
        with self._connect() as connection:
            count_rows = connection.execute(
                """
                SELECT rating, COUNT(*) AS count
                FROM consultation_feedback
                GROUP BY rating
                """
            ).fetchall()
            recent_rows = connection.execute(
                """
                SELECT *
                FROM consultation_feedback
                ORDER BY id DESC
                LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()
            issue_rows = connection.execute(
                "SELECT issue_types_json FROM consultation_feedback"
            ).fetchall()
            score_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS scored_feedback,
                    AVG(intent_score) AS average_intent_score,
                    AVG(draft_score) AS average_draft_score
                FROM consultation_feedback
                WHERE intent_score BETWEEN 1 AND 5
                  AND draft_score BETWEEN 1 AND 5
                """
            ).fetchone()

        counts = {row["rating"]: int(row["count"]) for row in count_rows}
        helpful = counts.get("helpful", 0)
        needs_improvement = counts.get("needs_improvement", 0)
        total = helpful + needs_improvement
        issue_counts: dict[str, int] = {}
        for row in issue_rows:
            try:
                issues = json.loads(row["issue_types_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(issues, list):
                continue
            for issue in issues:
                if isinstance(issue, str):
                    issue_counts[issue] = issue_counts.get(issue, 0) + 1

        recent = [
            FeedbackRecord(
                id=int(row["id"]),
                consultation_id=row["consultation_id"],
                rating=row["rating"],
                intent_score=int(row["intent_score"]),
                draft_score=int(row["draft_score"]),
                issue_types=json.loads(row["issue_types_json"]),
                note=row["note"],
                pii_masked=bool(row["pii_masked"]),
                pii_types=json.loads(row["pii_types_json"]),
                actor=row["actor"],
                created_at=row["created_at"],
            )
            for row in recent_rows
        ]
        return FeedbackSummary(
            total=total,
            helpful=helpful,
            needs_improvement=needs_improvement,
            helpful_rate=round(helpful / total, 4) if total else 0.0,
            scored_feedback=int(score_row["scored_feedback"] if score_row else 0),
            average_intent_score=round(
                float(score_row["average_intent_score"] or 0), 2
            ) if score_row else 0.0,
            average_draft_score=round(
                float(score_row["average_draft_score"] or 0), 2
            ) if score_row else 0.0,
            issue_counts=issue_counts,
            recent=recent,
        )

    def feedback_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM consultation_feedback"
            ).fetchone()
        return int(row["count"] if row else 0)
