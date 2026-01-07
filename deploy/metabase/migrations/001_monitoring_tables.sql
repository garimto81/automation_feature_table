-- =============================================================================
-- PRD-0008: 모니터링 대시보드 테이블 마이그레이션
-- Version: 001
-- Date: 2026-01-07
-- =============================================================================

-- 트랜잭션 시작
BEGIN;

-- =============================================================================
-- 1. table_status - 테이블 실시간 상태
-- =============================================================================

CREATE TABLE IF NOT EXISTS table_status (
    id SERIAL PRIMARY KEY,
    table_id VARCHAR(50) NOT NULL UNIQUE,

    -- Connection status
    primary_connected BOOLEAN DEFAULT FALSE,
    secondary_connected BOOLEAN DEFAULT FALSE,

    -- Current hand info
    current_hand_id INTEGER,
    current_hand_number INTEGER,
    hand_start_time TIMESTAMP,

    -- Fusion status: validated, review, manual
    last_fusion_result VARCHAR(20),

    -- Timestamps
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_table_status_table_id ON table_status(table_id);

COMMENT ON TABLE table_status IS 'PRD-0008: Real-time table status for monitoring dashboard';
COMMENT ON COLUMN table_status.primary_connected IS 'PokerGFX RFID 연결 상태';
COMMENT ON COLUMN table_status.secondary_connected IS 'Gemini AI 연결 상태';
COMMENT ON COLUMN table_status.last_fusion_result IS 'Fusion 결과: validated, review, manual';

-- =============================================================================
-- 2. system_health_log - 시스템 헬스 로그
-- =============================================================================

CREATE TABLE IF NOT EXISTS system_health_log (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL,

    -- Status: connected, disconnected, error, warning
    status VARCHAR(20) NOT NULL,

    -- Metrics
    latency_ms INTEGER,
    details JSONB,

    -- Message
    message TEXT,

    -- Timestamp
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_log_service ON system_health_log(service_name);
CREATE INDEX IF NOT EXISTS idx_health_log_created ON system_health_log(created_at);
CREATE INDEX IF NOT EXISTS idx_health_log_status ON system_health_log(status);

COMMENT ON TABLE system_health_log IS 'PRD-0008: System health check logs for monitoring';
COMMENT ON COLUMN system_health_log.service_name IS 'PostgreSQL, PokerGFX, Gemini API, vMix 등';
COMMENT ON COLUMN system_health_log.status IS 'connected, disconnected, error, warning';

-- =============================================================================
-- 3. recording_sessions - 녹화 세션
-- =============================================================================

CREATE TABLE IF NOT EXISTS recording_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE,
    table_id VARCHAR(50) NOT NULL,

    -- Status: recording, stopped, completed, error
    status VARCHAR(20) NOT NULL DEFAULT 'recording',

    -- Timing
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,

    -- File info
    file_size_mb DECIMAL(10, 2),
    file_path VARCHAR(500),

    -- vMix info
    vmix_input INTEGER,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recording_session_id ON recording_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_recording_table_id ON recording_sessions(table_id);
CREATE INDEX IF NOT EXISTS idx_recording_status ON recording_sessions(status);
CREATE INDEX IF NOT EXISTS idx_recording_start ON recording_sessions(start_time);

COMMENT ON TABLE recording_sessions IS 'PRD-0008: Recording session tracking for monitoring';
COMMENT ON COLUMN recording_sessions.status IS 'recording, stopped, completed, error';

-- =============================================================================
-- 4. 오래된 헬스 로그 정리용 함수
-- =============================================================================

CREATE OR REPLACE FUNCTION cleanup_old_health_logs(retention_hours INTEGER DEFAULT 24)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM system_health_log
    WHERE created_at < NOW() - (retention_hours || ' hours')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

COMMENT ON FUNCTION cleanup_old_health_logs IS 'PRD-0008: 오래된 헬스 로그 정리 (기본 24시간)';

-- =============================================================================
-- 5. 대시보드용 뷰
-- =============================================================================

-- 5.1 서비스별 최신 헬스 상태
CREATE OR REPLACE VIEW v_latest_health AS
SELECT DISTINCT ON (service_name)
    service_name,
    status,
    latency_ms,
    message,
    created_at
FROM system_health_log
ORDER BY service_name, created_at DESC;

COMMENT ON VIEW v_latest_health IS 'PRD-0008: 서비스별 최신 헬스 상태';

-- 5.2 오늘의 등급 분포
CREATE OR REPLACE VIEW v_today_grade_distribution AS
SELECT
    g.grade,
    COUNT(*) AS hand_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS percentage
FROM grades g
JOIN hands h ON g.hand_id = h.id
WHERE h.started_at >= CURRENT_DATE
GROUP BY g.grade
ORDER BY g.grade;

COMMENT ON VIEW v_today_grade_distribution IS 'PRD-0008: 오늘의 핸드 등급 분포';

-- 5.3 대시보드 요약
CREATE OR REPLACE VIEW v_dashboard_summary AS
SELECT
    (SELECT COUNT(*) FROM hands WHERE started_at >= CURRENT_DATE) AS today_hands,
    (SELECT COUNT(*) FROM grades g JOIN hands h ON g.hand_id = h.id
     WHERE g.broadcast_eligible = TRUE AND h.started_at >= CURRENT_DATE) AS broadcast_eligible,
    (SELECT COUNT(*) FROM recording_sessions WHERE status = 'recording') AS active_recordings,
    (SELECT COALESCE(ROUND(SUM(file_size_mb) / 1024.0, 2), 0)
     FROM recording_sessions WHERE status = 'completed' AND end_time >= CURRENT_DATE) AS today_storage_gb,
    (SELECT CASE WHEN COUNT(*) = SUM(CASE WHEN status = 'connected' THEN 1 ELSE 0 END)
                 THEN 'healthy' ELSE 'degraded' END
     FROM v_latest_health) AS system_status;

COMMENT ON VIEW v_dashboard_summary IS 'PRD-0008: 대시보드 핵심 지표 요약';

-- =============================================================================
-- 마이그레이션 기록
-- =============================================================================

CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    applied_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO _migrations (version, name)
VALUES ('001', 'monitoring_tables')
ON CONFLICT (version) DO NOTHING;

-- 트랜잭션 커밋
COMMIT;

-- =============================================================================
-- 확인 쿼리
-- =============================================================================

-- SELECT version, name, applied_at FROM _migrations ORDER BY version;
-- \dt table_status
-- \dt system_health_log
-- \dt recording_sessions
