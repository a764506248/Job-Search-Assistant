from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..database import db_connect, table_exists

TERMINAL_JOB_STATES = {"delivered", "skipped", "failed", "uncertain"}


class CodexDeliveryRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with db_connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    key_prefix TEXT NOT NULL UNIQUE,
                    key_hash TEXT NOT NULL UNIQUE,
                    scopes_json TEXT NOT NULL,
                    expires_at TEXT,
                    last_used_at TEXT,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_api_keys_user
                    ON agent_api_keys(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS codex_delivery_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    version INTEGER NOT NULL DEFAULT 1,
                    source_tabs_json TEXT NOT NULL,
                    job_intentions_json TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    city_code TEXT,
                    city_name TEXT,
                    experience_json TEXT NOT NULL,
                    degree_json TEXT NOT NULL,
                    company_scale_json TEXT NOT NULL,
                    boss_activity_json TEXT,
                    salary_mode TEXT NOT NULL,
                    salary_code TEXT,
                    salary_min_k INTEGER,
                    salary_max_k INTEGER,
                    benefits_json TEXT NOT NULL,
                    financing_json TEXT NOT NULL,
                    industries_json TEXT NOT NULL,
                    recommended_tags_json TEXT NOT NULL,
                    target_delivery_count INTEGER NOT NULL,
                    max_scan_count INTEGER NOT NULL,
                    interval_seconds REAL NOT NULL,
                    minimum_score INTEGER NOT NULL,
                    minimum_customization_confidence INTEGER NOT NULL,
                    resume_id INTEGER,
                    send_resume INTEGER NOT NULL DEFAULT 0,
                    greeting_strategy TEXT NOT NULL,
                    fallback_greeting TEXT NOT NULL,
                    confirmation_mode TEXT NOT NULL,
                    stop_on_uncertain INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_codex_configs_user
                    ON codex_delivery_configs(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS codex_delivery_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    config_id INTEGER,
                    config_snapshot_json TEXT NOT NULL,
                    trigger_source TEXT NOT NULL DEFAULT 'codex',
                    status TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    current_source_tab TEXT,
                    current_job_id TEXT,
                    target_delivery_count INTEGER NOT NULL,
                    scanned_count INTEGER NOT NULL DEFAULT 0,
                    captured_count INTEGER NOT NULL DEFAULT 0,
                    analyzed_count INTEGER NOT NULL DEFAULT 0,
                    eligible_count INTEGER NOT NULL DEFAULT 0,
                    delivered_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    uncertain_count INTEGER NOT NULL DEFAULT 0,
                    stop_reason TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_codex_runs_user
                    ON codex_delivery_runs(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS codex_delivery_job_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    run_id INTEGER NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'boss',
                    platform_job_id TEXT NOT NULL,
                    source_tab TEXT,
                    list_position INTEGER,
                    snapshot_json TEXT,
                    score INTEGER,
                    greeting_confidence INTEGER,
                    should_deliver INTEGER,
                    decision_reasons_json TEXT NOT NULL DEFAULT '[]',
                    matched_rules_json TEXT NOT NULL DEFAULT '[]',
                    risk_flags_json TEXT NOT NULL DEFAULT '[]',
                    greeting TEXT,
                    resume_id INTEGER,
                    status TEXT NOT NULL,
                    current_action TEXT,
                    idempotency_key TEXT,
                    result_json TEXT,
                    evidence_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, platform_job_id),
                    UNIQUE(idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_codex_steps_run
                    ON codex_delivery_job_steps(run_id, id);
                """
            )

    def create_key(
        self,
        user_id: int,
        name: str,
        scopes: list[str],
        expires_in_days: int | None,
        base_url: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        self.initialize()
        prefix = secrets.token_hex(6)
        secret = secrets.token_urlsafe(32)
        if base_url:
            encoded_url = urlsafe_b64encode(base_url.encode("utf-8")).decode("ascii").rstrip("=")
            plaintext = f"jsa_agent_v2_{encoded_url}_{prefix}_{secret}"
        else:
            plaintext = f"jsa_agent_{prefix}_{secret}"
        now = datetime.now(UTC)
        expires_at = (
            (now + timedelta(days=expires_in_days)).isoformat() if expires_in_days else None
        )
        with db_connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO agent_api_keys(
                    user_id, name, key_prefix, key_hash, scopes_json, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    user_id,
                    name.strip(),
                    prefix,
                    self._key_hash(plaintext),
                    self._json(scopes),
                    expires_at,
                    now.isoformat(),
                ),
            )
            key_id = int(cursor.lastrowid)
        return self.get_key(key_id, user_id=user_id), plaintext

    def authenticate_key(self, plaintext: str, required_scope: str) -> dict[str, Any] | None:
        self.initialize()
        if not plaintext.startswith("jsa_agent_"):
            return None
        digest = self._key_hash(plaintext)
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT * FROM agent_api_keys WHERE key_hash = ? AND revoked_at IS NULL
                AND (expires_at IS NULL OR expires_at > ?)""",
                (digest, now),
            ).fetchone()
            if row is None or not hmac.compare_digest(str(row["key_hash"]), digest):
                return None
            scopes = self._loads(row["scopes_json"], [])
            if required_scope not in scopes:
                return None
            connection.execute(
                "UPDATE agent_api_keys SET last_used_at = ? WHERE id = ?", (now, row["id"])
            )
            result = self._key_row(row)
            result["scopes"] = scopes
            result["userId"] = int(row["user_id"])
            return result

    def list_keys(self, user_id: int) -> list[dict[str, Any]]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM agent_api_keys WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [self._key_row(row) for row in rows]

    def get_key(self, key_id: int, *, user_id: int) -> dict[str, Any]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM agent_api_keys WHERE id = ? AND user_id = ?", (key_id, user_id)
            ).fetchone()
        if row is None:
            raise KeyError(key_id)
        return self._key_row(row)

    def revoke_key(self, key_id: int, *, user_id: int) -> dict[str, Any]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE agent_api_keys SET revoked_at = ? WHERE id = ? AND user_id = ?",
                (datetime.now(UTC).isoformat(), key_id, user_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(key_id)
        return self.get_key(key_id, user_id=user_id)

    def save_config(
        self, user_id: int, payload: dict[str, Any], config_id: int | None = None
    ) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        values = self._config_values(payload)
        with db_connect(self.database_path) as connection:
            if config_id is not None:
                owned = connection.execute(
                    "SELECT 1 FROM codex_delivery_configs WHERE id = ? AND user_id = ?",
                    (config_id, user_id),
                ).fetchone()
                if owned is None:
                    raise KeyError(config_id)
            if payload["is_default"]:
                connection.execute(
                    "UPDATE codex_delivery_configs SET is_default = 0 WHERE user_id = ?",
                    (user_id,),
                )
            if config_id is None:
                cursor = connection.execute(
                    f"""INSERT INTO codex_delivery_configs(
                        user_id, {", ".join(values)}, created_at, updated_at
                    ) VALUES (?, {", ".join("?" for _ in values)}, ?, ?) RETURNING id""",
                    (user_id, *values.values(), now, now),
                )
                config_id = int(cursor.lastrowid)
            else:
                assignments = ", ".join(f"{name} = ?" for name in values)
                cursor = connection.execute(
                    f"""UPDATE codex_delivery_configs SET {assignments},
                    version = version + 1, updated_at = ? WHERE id = ? AND user_id = ?""",
                    (*values.values(), now, config_id, user_id),
                )
                if cursor.rowcount == 0:
                    raise KeyError(config_id)
        return self.get_config(config_id, user_id=user_id)

    def list_configs(self, user_id: int) -> list[dict[str, Any]]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT * FROM codex_delivery_configs WHERE user_id = ?
                ORDER BY is_default DESC, updated_at DESC""",
                (user_id,),
            ).fetchall()
        return [self._config_row(row) for row in rows]

    def get_config(self, config_id: int, *, user_id: int) -> dict[str, Any]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM codex_delivery_configs WHERE id = ? AND user_id = ?",
                (config_id, user_id),
            ).fetchone()
        if row is None:
            raise KeyError(config_id)
        return self._config_row(row)

    def default_config(self, user_id: int) -> dict[str, Any] | None:
        configs = self.list_configs(user_id)
        return next(
            (item for item in configs if item["isDefault"]), configs[0] if configs else None
        )

    def delete_config(self, config_id: int, *, user_id: int) -> None:
        self.initialize()
        with db_connect(self.database_path) as connection:
            used = connection.execute(
                "SELECT 1 FROM codex_delivery_runs WHERE config_id = ? AND user_id = ? LIMIT 1",
                (config_id, user_id),
            ).fetchone()
            if used:
                raise ValueError("该配置已被运行引用，不能删除")
            cursor = connection.execute(
                "DELETE FROM codex_delivery_configs WHERE id = ? AND user_id = ?",
                (config_id, user_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(config_id)

    def create_run(self, user_id: int, config: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO codex_delivery_runs(
                    user_id, config_id, config_snapshot_json, status, current_stage,
                    target_delivery_count, started_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'running', 'opening_boss', ?, ?, ?, ?) RETURNING id""",
                (
                    user_id,
                    config["id"],
                    self._json(config),
                    config["targetDeliveryCount"],
                    now,
                    now,
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)
        return self.get_run(run_id, user_id=user_id)

    def list_runs(self, user_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        self.initialize()
        limit = max(1, min(limit, 20))
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM codex_delivery_runs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def get_run(self, run_id: int, *, user_id: int, include_steps: bool = False) -> dict[str, Any]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM codex_delivery_runs WHERE id = ? AND user_id = ?",
                (run_id, user_id),
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            result = self._run_row(row)
            if include_steps:
                steps = connection.execute(
                    """SELECT * FROM codex_delivery_job_steps
                    WHERE run_id = ? AND user_id = ? ORDER BY id""",
                    (run_id, user_id),
                ).fetchall()
                result["steps"] = [self._step_row(step) for step in steps]
            return result

    def check_job(
        self,
        user_id: int,
        run_id: int,
        platform_job_id: str,
        source_tab: str,
        list_position: int | None,
    ) -> tuple[dict[str, Any], bool]:
        run = self._assert_running(run_id, user_id)
        self.initialize()
        now = datetime.now(UTC).isoformat()
        duplicate = False
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT * FROM codex_delivery_job_steps
                WHERE run_id = ? AND platform_job_id = ?""",
                (run_id, platform_job_id),
            ).fetchone()
            if row is None:
                if run["scannedCount"] >= run["configSnapshot"]["maxScanCount"]:
                    raise ValueError("已达到最大扫描职位数")
                active = connection.execute(
                    """SELECT platform_job_id FROM codex_delivery_job_steps
                    WHERE run_id = ? AND status IN (
                        'discovered', 'captured', 'eligible', 'rejected', 'opening_chat'
                    ) LIMIT 1""",
                    (run_id,),
                ).fetchone()
                if active is not None:
                    raise ValueError(f"请先完成岗位 {active['platform_job_id']} 的处理")
                duplicate = connection.execute(
                    """SELECT 1 FROM codex_delivery_job_steps
                    WHERE user_id = ? AND platform_job_id = ?
                    AND (status = 'delivered' OR
                         (status = 'skipped' AND
                          json_extract(evidence_json, '$.priorCommunication') = 1))
                    LIMIT 1""",
                    (user_id, platform_job_id),
                ).fetchone()
                if duplicate is None and table_exists(connection, "delivery_records"):
                    duplicate = connection.execute(
                        """SELECT 1 FROM delivery_records
                        WHERE user_id = ? AND platform = 'boss'
                        AND platform_job_id IN (?, ?)
                        AND status IN ('delivered', 'greeting_sent') LIMIT 1""",
                        (user_id, platform_job_id, f"codex-phone:{platform_job_id}"),
                    ).fetchone()
                initial_status = "skipped" if duplicate else "discovered"
                initial_action = "next_job" if duplicate else "capture"
                cursor = connection.execute(
                    """INSERT INTO codex_delivery_job_steps(
                        user_id, run_id, platform_job_id, source_tab, list_position,
                        status, current_action, decision_reasons_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                    (
                        user_id,
                        run_id,
                        platform_job_id,
                        source_tab,
                        list_position,
                        initial_status,
                        initial_action,
                        self._json(["该岗位已有明确沟通记录"]) if duplicate else "[]",
                        now,
                        now,
                    ),
                )
                step_id = int(cursor.lastrowid)
                connection.execute(
                    """UPDATE codex_delivery_runs SET scanned_count = scanned_count + 1,
                    skipped_count = skipped_count + ?, current_stage = ?,
                    current_source_tab = ?, current_job_id = ?,
                    updated_at = ? WHERE id = ? AND user_id = ?""",
                    (
                        int(bool(duplicate)),
                        "scanning" if duplicate else "capturing",
                        source_tab,
                        platform_job_id,
                        now,
                        run_id,
                        user_id,
                    ),
                )
                duplicate = bool(duplicate)
                if duplicate and run["scannedCount"] + 1 >= run["configSnapshot"]["maxScanCount"]:
                    connection.execute(
                        """UPDATE codex_delivery_runs SET status = 'stopped',
                        current_stage = 'finished', stop_reason = 'scan_limit_reached',
                        finished_at = ?, updated_at = ? WHERE id = ? AND user_id = ?""",
                        (now, now, run_id, user_id),
                    )
            else:
                step_id = int(row["id"])
                duplicate = row["status"] in TERMINAL_JOB_STATES
        return self.get_step(step_id, user_id=user_id), duplicate

    def capture_job(
        self, user_id: int, run_id: int, step_id: int, snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        step = self.get_step(step_id, user_id=user_id)
        if step["runId"] != run_id:
            raise KeyError(step_id)
        if step["status"] not in {"discovered", "captured"}:
            raise ValueError(f"当前状态 {step['status']} 不能采集")
        first_capture = step["status"] == "discovered"
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE codex_delivery_job_steps SET snapshot_json = ?, status = 'captured',
                current_action = 'analyze', updated_at = ? WHERE id = ? AND user_id = ?""",
                (self._json(snapshot), now, step_id, user_id),
            )
            if first_capture:
                connection.execute(
                    """UPDATE codex_delivery_runs SET captured_count = captured_count + 1,
                    current_stage = 'analyzing', updated_at = ? WHERE id = ? AND user_id = ?""",
                    (now, run_id, user_id),
                )
        return self.get_step(step_id, user_id=user_id)

    def link_job_snapshot(
        self, user_id: int, run_id: int, step_id: int, snapshot_id: int
    ) -> dict[str, Any]:
        step = self.get_step(step_id, user_id=user_id)
        if step["runId"] != run_id or step["status"] != "captured":
            raise ValueError("岗位未采集，不能关联职位快照")
        snapshot = dict(step["snapshot"] or {})
        snapshot["pcSnapshotId"] = snapshot_id
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE codex_delivery_job_steps SET snapshot_json = ?, updated_at = ?
                WHERE id = ? AND user_id = ?""",
                (self._json(snapshot), now, step_id, user_id),
            )
        return self.get_step(step_id, user_id=user_id)

    def prepare_job(
        self,
        user_id: int,
        run_id: int,
        step_id: int,
        platform_job_id: str,
        observed_title: str,
        observed_company_name: str,
        user_confirmed: bool,
    ) -> dict[str, Any]:
        self._assert_running(run_id, user_id)
        step = self.get_step(step_id, user_id=user_id)
        if step["runId"] != run_id or step["status"] != "eligible":
            raise ValueError("岗位尚未通过分析或状态不允许准备发送")
        snapshot = step["snapshot"] or {}
        expected = (
            step["platformJobId"],
            self._normalize_identity(snapshot.get("title")),
            self._normalize_company_identity(snapshot.get("companyName")),
        )
        observed = (
            platform_job_id,
            self._normalize_identity(observed_title),
            self._normalize_company_identity(observed_company_name),
        )
        if expected[0] != observed[0]:
            raise ValueError("岗位标识与快照不一致，不能发送")
        if expected[1] != observed[1]:
            raise ValueError("岗位标题与快照不一致，不能发送")
        if expected[2] != observed[2]:
            raise ValueError("公司名称与快照不一致，不能发送")
        run = self.get_run(run_id, user_id=user_id)
        if run["configSnapshot"].get("confirmationMode") == "per_job" and not user_confirmed:
            raise ValueError("当前配置要求每岗确认，尚未取得本岗位用户确认")
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE codex_delivery_job_steps SET status = 'opening_chat',
                current_action = 'send_greeting', result_json = ?, updated_at = ?
                WHERE id = ? AND user_id = ?""",
                (
                    self._json({"identityVerified": True, "verifiedAt": now}),
                    now,
                    step_id,
                    user_id,
                ),
            )
            connection.execute(
                """UPDATE codex_delivery_runs SET current_stage = 'sending', updated_at = ?
                WHERE id = ? AND user_id = ?""",
                (now, run_id, user_id),
            )
        return self.get_step(step_id, user_id=user_id)

    def save_analysis(
        self,
        user_id: int,
        run_id: int,
        step_id: int,
        *,
        score: int,
        confidence: int,
        should_deliver: bool,
        reasons: list[str],
        rules: list[dict[str, Any]],
        risks: list[str],
        greeting: str,
        resume_id: int | None,
    ) -> dict[str, Any]:
        step = self.get_step(step_id, user_id=user_id)
        if step["runId"] != run_id or step["status"] not in {
            "captured",
            "analyzed",
            "eligible",
            "rejected",
        }:
            raise ValueError("岗位尚未采集或状态不允许分析")
        first_analysis = step["score"] is None
        next_status = "eligible" if should_deliver else "rejected"
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE codex_delivery_job_steps SET score = ?, greeting_confidence = ?,
                should_deliver = ?, decision_reasons_json = ?, matched_rules_json = ?,
                risk_flags_json = ?, greeting = ?, resume_id = ?, status = ?,
                current_action = ?, updated_at = ? WHERE id = ? AND user_id = ?""",
                (
                    score,
                    confidence,
                    int(should_deliver),
                    self._json(reasons),
                    self._json(rules),
                    self._json(risks),
                    greeting,
                    resume_id,
                    next_status,
                    "open_chat" if should_deliver else "next_job",
                    now,
                    step_id,
                    user_id,
                ),
            )
            if first_analysis:
                connection.execute(
                    """UPDATE codex_delivery_runs SET analyzed_count = analyzed_count + 1,
                    eligible_count = eligible_count + ?, current_stage = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?""",
                    (
                        int(should_deliver),
                        "ready_to_deliver" if should_deliver else "scanning",
                        now,
                        run_id,
                        user_id,
                    ),
                )
        return self.get_step(step_id, user_id=user_id)

    def save_result(
        self,
        user_id: int,
        run_id: int,
        step_id: int,
        outcome: str,
        idempotency_key: str,
        evidence: dict[str, Any],
        error_message: str | None,
    ) -> dict[str, Any]:
        run = self.get_run(run_id, user_id=user_id)
        step = self.get_step(step_id, user_id=user_id)
        if step["runId"] != run_id:
            raise KeyError(step_id)
        if step["idempotencyKey"]:
            if step["idempotencyKey"] != idempotency_key:
                raise ValueError("该岗位已经使用另一个幂等键完成")
            if step["status"] != outcome:
                raise ValueError("同一幂等键不能修改已记录的结果")
            return step
        if run["status"] != "running":
            raise ValueError("任务已经停止，不能再记录新结果")
        if outcome == "delivered":
            if step["status"] != "opening_chat":
                raise ValueError("发送前必须核对岗位详情")
            if evidence.get("messageVisible") is not True:
                raise ValueError("缺少可验证的问候语已发送证据")
            if evidence.get("inputMethod") not in {
                "pua_type_text",
                "wda_keys",
                "universal_clipboard",
                "first_common_phrase",
            }:
                raise ValueError("缺少有效的问候语输入方式证据")
            if not str(evidence.get("sentText") or "").strip():
                raise ValueError("缺少实际发送的完整问候语")
            if run["configSnapshot"].get("sendResume"):
                resume_outcome = evidence.get("resumeOutcome")
                if resume_outcome not in {"sent", "failed", "not_available"}:
                    raise ValueError("当前计划要求发送简历，缺少简历处理结果")
                if resume_outcome == "sent" and evidence.get("resumeVisible") is not True:
                    raise ValueError("缺少简历已发送的可见证据")
        elif outcome == "skipped":
            if step["status"] not in {"rejected", "eligible", "opening_chat"}:
                raise ValueError("只有已分析的岗位可以跳过")
            if step["status"] == "opening_chat" and evidence.get("priorCommunication") is not True:
                raise ValueError("打开沟通后仅能因已核实的历史沟通而跳过")
            if evidence.get("priorCommunication") is True and evidence.get("source") not in {
                "boss_detail_status",
                "boss_chat_history",
            }:
                raise ValueError("历史沟通跳过缺少 BOSS 页面证据来源")
        elif outcome in {"failed", "uncertain"} and step["status"] not in {
            "discovered",
            "captured",
            "eligible",
            "rejected",
            "opening_chat",
        }:
            raise ValueError("当前岗位状态不能记录失败或不确定结果")
        if step["status"] in TERMINAL_JOB_STATES:
            raise ValueError("该岗位已经结束")
        count_column = {
            "delivered": "delivered_count",
            "skipped": "skipped_count",
            "failed": "failed_count",
            "uncertain": "uncertain_count",
        }[outcome]
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            try:
                connection.execute(
                    """UPDATE codex_delivery_job_steps SET status = ?, current_action = 'next_job',
                    idempotency_key = ?, result_json = ?, evidence_json = ?, error_message = ?,
                    updated_at = ? WHERE id = ? AND user_id = ?""",
                    (
                        outcome,
                        idempotency_key,
                        self._json({"outcome": outcome}),
                        self._json(evidence),
                        error_message,
                        now,
                        step_id,
                        user_id,
                    ),
                )
            except Exception as error:
                if "unique" in str(error).lower():
                    raise ValueError("幂等键已被使用") from error
                raise
            connection.execute(
                f"""UPDATE codex_delivery_runs SET {count_column} = {count_column} + 1,
                current_stage = 'scanning', updated_at = ? WHERE id = ? AND user_id = ?""",
                (now, run_id, user_id),
            )
            delivered = run["deliveredCount"] + int(outcome == "delivered")
            config = run["configSnapshot"]
            if delivered >= run["targetDeliveryCount"]:
                connection.execute(
                    """UPDATE codex_delivery_runs SET status = 'completed',
                    current_stage = 'finished', stop_reason = 'target_reached',
                    finished_at = ?, updated_at = ? WHERE id = ? AND user_id = ?""",
                    (now, now, run_id, user_id),
                )
            elif outcome == "uncertain" and config.get("stopOnUncertain", True):
                connection.execute(
                    """UPDATE codex_delivery_runs SET status = 'uncertain',
                    current_stage = 'finished', stop_reason = 'uncertain_result',
                    finished_at = ?, updated_at = ? WHERE id = ? AND user_id = ?""",
                    (now, now, run_id, user_id),
                )
            elif run["scannedCount"] >= config.get("maxScanCount", 20):
                connection.execute(
                    """UPDATE codex_delivery_runs SET status = 'stopped',
                    current_stage = 'finished', stop_reason = 'scan_limit_reached',
                    finished_at = ?, updated_at = ? WHERE id = ? AND user_id = ?""",
                    (now, now, run_id, user_id),
                )
        return self.get_step(step_id, user_id=user_id)

    def get_step(self, step_id: int, *, user_id: int) -> dict[str, Any]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM codex_delivery_job_steps WHERE id = ? AND user_id = ?",
                (step_id, user_id),
            ).fetchone()
        if row is None:
            raise KeyError(step_id)
        return self._step_row(row)

    def finish_run(
        self, run_id: int, user_id: int, status: str, reason: str | None
    ) -> dict[str, Any]:
        run = self.get_run(run_id, user_id=user_id)
        if run["status"] not in {"running", "paused"}:
            raise ValueError(f"运行当前状态为 {run['status']}，不能再次结束")
        if status == "completed" and run["deliveredCount"] < run["targetDeliveryCount"]:
            raise ValueError("成功投递数未达到目标，不能标记为已完成")
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE codex_delivery_runs SET status = ?, current_stage = 'finished',
                stop_reason = ?, finished_at = ?, updated_at = ? WHERE id = ? AND user_id = ?""",
                (status, reason, now, now, run_id, user_id),
            )
        return self.get_run(run_id, user_id=user_id, include_steps=True)

    def pause_run(self, run_id: int, user_id: int) -> dict[str, Any]:
        self.get_run(run_id, user_id=user_id)
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE codex_delivery_runs SET status = 'paused', current_stage = 'paused',
                updated_at = ? WHERE id = ? AND user_id = ? AND status = 'running'""",
                (datetime.now(UTC).isoformat(), run_id, user_id),
            )
        return self.get_run(run_id, user_id=user_id, include_steps=True)

    def _assert_running(self, run_id: int, user_id: int) -> dict[str, Any]:
        run = self.get_run(run_id, user_id=user_id)
        if run["status"] != "running":
            raise ValueError(f"运行当前状态为 {run['status']}，不能继续处理岗位")
        return run

    @staticmethod
    def _normalize_identity(value: object) -> str:
        return "".join(str(value or "").casefold().split())

    @classmethod
    def _normalize_company_identity(cls, value: object) -> str:
        name = cls._normalize_identity(value)
        for suffix in ("股份有限公司", "有限责任公司", "有限公司", "股份公司"):
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[: -len(suffix)]
        return name

    @staticmethod
    def _key_hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _loads(value: str | None, default: Any) -> Any:
        return json.loads(value) if value else default

    @classmethod
    def _key_row(cls, row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "keyPrefix": row["key_prefix"],
            "scopes": cls._loads(row["scopes_json"], []),
            "expiresAt": row["expires_at"],
            "lastUsedAt": row["last_used_at"],
            "revokedAt": row["revoked_at"],
            "createdAt": row["created_at"],
        }

    @classmethod
    def _config_values(cls, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": data["name"],
            "is_default": int(data["is_default"]),
            "enabled": int(data["enabled"]),
            "source_tabs_json": cls._json(data["source_tabs"]),
            "job_intentions_json": cls._json(data["job_intentions"]),
            "keywords_json": cls._json(data["keywords"]),
            "city_code": data["city_code"],
            "city_name": data["city_name"],
            "experience_json": cls._json(data["experience"]),
            "degree_json": cls._json(data["degree"]),
            "company_scale_json": cls._json(data["company_scale"]),
            "boss_activity_json": cls._json(data["boss_activity"])
            if data["boss_activity"]
            else None,
            "salary_mode": data["salary_mode"],
            "salary_code": data["salary_code"],
            "salary_min_k": data["salary_min_k"],
            "salary_max_k": data["salary_max_k"],
            "benefits_json": cls._json(data["benefits"]),
            "financing_json": cls._json(data["financing"]),
            "industries_json": cls._json(data["industries"]),
            "recommended_tags_json": cls._json(data["recommended_tags"]),
            "target_delivery_count": data["target_delivery_count"],
            "max_scan_count": data["max_scan_count"],
            "interval_seconds": data["interval_seconds"],
            "minimum_score": data["minimum_score"],
            "minimum_customization_confidence": data["minimum_customization_confidence"],
            "resume_id": data["resume_id"],
            "send_resume": int(data["send_resume"]),
            "greeting_strategy": data["greeting_strategy"],
            "fallback_greeting": data["fallback_greeting"],
            "confirmation_mode": data["confirmation_mode"],
            "stop_on_uncertain": int(data["stop_on_uncertain"]),
        }

    @classmethod
    def _config_row(cls, row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "isDefault": bool(row["is_default"]),
            "enabled": bool(row["enabled"]),
            "version": int(row["version"]),
            "sourceTabs": cls._loads(row["source_tabs_json"], []),
            "jobIntentions": cls._loads(row["job_intentions_json"], []),
            "keywords": cls._loads(row["keywords_json"], []),
            "cityCode": row["city_code"],
            "cityName": row["city_name"],
            "experience": cls._loads(row["experience_json"], []),
            "degree": cls._loads(row["degree_json"], []),
            "companyScale": cls._loads(row["company_scale_json"], []),
            "bossActivity": cls._loads(row["boss_activity_json"], None),
            "salaryMode": row["salary_mode"],
            "salaryCode": row["salary_code"],
            "salaryMinK": row["salary_min_k"],
            "salaryMaxK": row["salary_max_k"],
            "benefits": cls._loads(row["benefits_json"], []),
            "financing": cls._loads(row["financing_json"], []),
            "industries": cls._loads(row["industries_json"], []),
            "recommendedTags": cls._loads(row["recommended_tags_json"], []),
            "targetDeliveryCount": int(row["target_delivery_count"]),
            "maxScanCount": int(row["max_scan_count"]),
            "intervalSeconds": float(row["interval_seconds"]),
            "minimumScore": int(row["minimum_score"]),
            "minimumCustomizationConfidence": int(row["minimum_customization_confidence"]),
            "resumeId": row["resume_id"],
            "sendResume": bool(row["send_resume"]),
            "greetingStrategy": row["greeting_strategy"],
            "fallbackGreeting": row["fallback_greeting"],
            "confirmationMode": row["confirmation_mode"],
            "stopOnUncertain": bool(row["stop_on_uncertain"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @classmethod
    def _run_row(cls, row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "configId": row["config_id"],
            "configSnapshot": cls._loads(row["config_snapshot_json"], {}),
            "triggerSource": row["trigger_source"],
            "status": row["status"],
            "currentStage": row["current_stage"],
            "currentSourceTab": row["current_source_tab"],
            "currentJobId": row["current_job_id"],
            "targetDeliveryCount": int(row["target_delivery_count"]),
            "scannedCount": int(row["scanned_count"]),
            "capturedCount": int(row["captured_count"]),
            "analyzedCount": int(row["analyzed_count"]),
            "eligibleCount": int(row["eligible_count"]),
            "deliveredCount": int(row["delivered_count"]),
            "skippedCount": int(row["skipped_count"]),
            "failedCount": int(row["failed_count"]),
            "uncertainCount": int(row["uncertain_count"]),
            "stopReason": row["stop_reason"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @classmethod
    def _step_row(cls, row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "runId": int(row["run_id"]),
            "platform": row["platform"],
            "platformJobId": row["platform_job_id"],
            "sourceTab": row["source_tab"],
            "listPosition": row["list_position"],
            "snapshot": cls._loads(row["snapshot_json"], None),
            "score": row["score"],
            "greetingConfidence": row["greeting_confidence"],
            "shouldDeliver": None if row["should_deliver"] is None else bool(row["should_deliver"]),
            "decisionReasons": cls._loads(row["decision_reasons_json"], []),
            "matchedRules": cls._loads(row["matched_rules_json"], []),
            "riskFlags": cls._loads(row["risk_flags_json"], []),
            "greeting": row["greeting"],
            "resumeId": row["resume_id"],
            "status": row["status"],
            "currentAction": row["current_action"],
            "idempotencyKey": row["idempotency_key"],
            "result": cls._loads(row["result_json"], None),
            "evidence": cls._loads(row["evidence_json"], None),
            "errorMessage": row["error_message"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
