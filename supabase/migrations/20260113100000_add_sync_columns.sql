-- Migration: Add sync tracking columns to gfx_sessions
-- Issue: #6, #8 - sync_source 컬럼 누락으로 동기화 실패
-- Date: 2026-01-13

-- Add sync_source column (동기화 출처)
-- 값: gfx_pc_direct, nas_upload, manual_import 등
ALTER TABLE gfx_sessions
ADD COLUMN IF NOT EXISTS sync_source TEXT DEFAULT 'unknown';

-- Add sync_status column (동기화 상태)
-- 값: synced, pending, failed
ALTER TABLE gfx_sessions
ADD COLUMN IF NOT EXISTS sync_status TEXT DEFAULT 'synced';

-- Add file_path column (파일 경로 - 복구용)
-- 배치 실패 시 재시도에 사용
ALTER TABLE gfx_sessions
ADD COLUMN IF NOT EXISTS file_path TEXT;

-- Add index for sync status queries
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_sync_status
ON gfx_sessions(sync_status);

-- Add index for sync source filtering
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_sync_source
ON gfx_sessions(sync_source);

-- Comment for documentation
COMMENT ON COLUMN gfx_sessions.sync_source IS '동기화 출처: gfx_pc_direct, nas_upload, manual_import';
COMMENT ON COLUMN gfx_sessions.sync_status IS '동기화 상태: synced, pending, failed';
COMMENT ON COLUMN gfx_sessions.file_path IS '원본 파일 경로 (복구/디버깅용)';
