-- =============================================================================
-- PRD-0008: 모니터링 대시보드 SQL 쿼리
-- Metabase Questions 정의
-- =============================================================================

-- =============================================================================
-- 1. 테이블 상태 (실시간)
-- Question: Table Status Overview
-- Visualization: Table
-- =============================================================================

-- 1.1 현재 테이블 상태
SELECT
    table_id AS "테이블",
    CASE WHEN primary_connected THEN '● ON' ELSE '○ OFF' END AS "Primary",
    CASE WHEN secondary_connected THEN '● ON' ELSE '○ OFF' END AS "Secondary",
    current_hand_number AS "현재 핸드",
    CASE
        WHEN hand_start_time IS NULL THEN '-'
        ELSE TO_CHAR(NOW() - hand_start_time, 'MI:SS')
    END AS "진행 시간",
    COALESCE(last_fusion_result, '-') AS "Fusion 상태",
    TO_CHAR(updated_at, 'HH24:MI:SS') AS "업데이트"
FROM table_status
ORDER BY table_id;

-- =============================================================================
-- 2. 핸드 등급 분포
-- Question: Hand Grade Distribution
-- Visualization: Pie Chart / Bar Chart
-- =============================================================================

-- 2.1 오늘의 등급 분포
SELECT
    g.grade AS "등급",
    COUNT(*) AS "핸드 수",
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS "비율(%)"
FROM grades g
JOIN hands h ON g.hand_id = h.id
WHERE h.started_at >= CURRENT_DATE
GROUP BY g.grade
ORDER BY g.grade;

-- 2.2 방송 적합 핸드 (A+B 등급)
SELECT
    SUM(CASE WHEN g.grade IN ('A', 'B') THEN 1 ELSE 0 END) AS "방송 적합",
    SUM(CASE WHEN g.grade = 'C' THEN 1 ELSE 0 END) AS "비적합",
    COUNT(*) AS "전체",
    ROUND(
        SUM(CASE WHEN g.grade IN ('A', 'B') THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0), 1
    ) AS "적합 비율(%)"
FROM grades g
JOIN hands h ON g.hand_id = h.id
WHERE h.started_at >= CURRENT_DATE;

-- =============================================================================
-- 3. 최근 A등급 핸드
-- Question: Recent A-Grade Hands
-- Visualization: Table
-- =============================================================================

SELECT
    h.id,
    h.table_id AS "테이블",
    h.hand_number AS "핸드 번호",
    h.hand_rank AS "핸드 랭크",
    TO_CHAR(h.duration_seconds / 60, 'FM999') || ':' ||
        LPAD(CAST(h.duration_seconds % 60 AS TEXT), 2, '0') AS "진행 시간",
    TO_CHAR(h.started_at, 'HH24:MI:SS') AS "시작 시간"
FROM hands h
JOIN grades g ON h.id = g.hand_id
WHERE g.grade = 'A'
ORDER BY h.started_at DESC
LIMIT 10;

-- =============================================================================
-- 4. 시간대별 핸드 트렌드
-- Question: Hourly Hand Trend
-- Visualization: Line Chart
-- =============================================================================

SELECT
    DATE_TRUNC('hour', h.started_at) AS "시간",
    COUNT(*) AS "핸드 수",
    SUM(CASE WHEN g.grade = 'A' THEN 1 ELSE 0 END) AS "A등급",
    SUM(CASE WHEN g.grade = 'B' THEN 1 ELSE 0 END) AS "B등급",
    SUM(CASE WHEN g.grade = 'C' THEN 1 ELSE 0 END) AS "C등급"
FROM hands h
LEFT JOIN grades g ON h.id = g.hand_id
WHERE h.started_at >= CURRENT_DATE
GROUP BY DATE_TRUNC('hour', h.started_at)
ORDER BY "시간";

-- =============================================================================
-- 5. 녹화 세션
-- Question: Recording Sessions
-- Visualization: Table
-- =============================================================================

-- 5.1 활성 녹화 세션
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
WHERE status = 'recording'
ORDER BY start_time DESC;

-- 5.2 오늘 완료된 세션 요약
SELECT
    COUNT(*) AS "완료 세션",
    COALESCE(ROUND(SUM(file_size_mb) / 1024.0, 2), 0) AS "총 용량(GB)"
FROM recording_sessions
WHERE status = 'completed'
  AND end_time >= CURRENT_DATE;

-- =============================================================================
-- 6. 시스템 헬스
-- Question: System Health Status
-- Visualization: Table
-- =============================================================================

-- 6.1 최신 서비스 상태 (서비스별 최신 로그)
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
    COALESCE(message, '-') AS "메시지",
    TO_CHAR(created_at, 'HH24:MI:SS') AS "체크 시간"
FROM system_health_log l1
WHERE created_at = (
    SELECT MAX(created_at)
    FROM system_health_log l2
    WHERE l2.service_name = l1.service_name
)
ORDER BY service_name;

-- =============================================================================
-- 7. 에러 로그
-- Question: Recent Error Logs
-- Visualization: Table
-- =============================================================================

SELECT
    TO_CHAR(created_at, 'HH24:MI:SS') AS "시간",
    service_name AS "서비스",
    CASE status
        WHEN 'error' THEN '[ERROR]'
        WHEN 'warning' THEN '[WARN]'
        ELSE '[' || UPPER(status) || ']'
    END AS "레벨",
    COALESCE(message, '-') AS "메시지"
FROM system_health_log
WHERE status IN ('error', 'warning')
  AND created_at >= NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 20;

-- =============================================================================
-- 8. 대시보드 요약 스칼라 (개별 쿼리)
-- =============================================================================

-- 8.1 오늘 총 핸드 수
SELECT COUNT(*) AS "오늘 핸드"
FROM hands
WHERE started_at >= CURRENT_DATE;

-- 8.2 방송 적합 핸드 수
SELECT COUNT(*) AS "방송 적합"
FROM grades g
JOIN hands h ON g.hand_id = h.id
WHERE g.broadcast_eligible = TRUE
  AND h.started_at >= CURRENT_DATE;

-- 8.3 활성 녹화 세션 수
SELECT COUNT(*) AS "녹화 중"
FROM recording_sessions
WHERE status = 'recording';

-- 8.4 시스템 정상 여부 (모든 서비스 connected)
SELECT
    CASE
        WHEN COUNT(*) = COUNT(CASE WHEN status = 'connected' THEN 1 END) THEN '✓ 정상'
        ELSE '⚠ 점검 필요'
    END AS "시스템 상태"
FROM (
    SELECT DISTINCT ON (service_name) service_name, status
    FROM system_health_log
    ORDER BY service_name, created_at DESC
) latest;

-- =============================================================================
-- 9. 테이블별 통계
-- Question: Table Statistics
-- Visualization: Bar Chart
-- =============================================================================

SELECT
    h.table_id AS "테이블",
    COUNT(*) AS "핸드 수",
    SUM(CASE WHEN g.grade = 'A' THEN 1 ELSE 0 END) AS "A등급",
    SUM(CASE WHEN g.grade = 'B' THEN 1 ELSE 0 END) AS "B등급",
    ROUND(AVG(h.duration_seconds), 0) AS "평균 시간(초)"
FROM hands h
LEFT JOIN grades g ON h.id = g.hand_id
WHERE h.started_at >= CURRENT_DATE
GROUP BY h.table_id
ORDER BY h.table_id;
