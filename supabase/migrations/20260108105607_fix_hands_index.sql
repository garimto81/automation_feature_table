-- Drop the problematic index (Hands array too large for btree)
DROP INDEX IF EXISTS idx_gfx_sessions_hands_count;
