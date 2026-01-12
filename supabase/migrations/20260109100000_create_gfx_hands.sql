-- Create gfx_hands table for individual hand storage
-- Enables incremental sync: only new hands are added on file modification

CREATE TABLE IF NOT EXISTS gfx_hands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id BIGINT NOT NULL,           -- PokerGFX session ID (Windows FileTime)
    hand_id BIGINT NOT NULL UNIQUE,       -- PokerGFX hand ID (unique across all sessions)
    hand_number INT,                      -- Hand number within session
    hand_data JSONB NOT NULL,             -- Individual hand JSON data
    board_cards TEXT[],                   -- Community cards array
    player_count INT,                     -- Number of players in hand
    created_at TIMESTAMPTZ DEFAULT now(),
    synced_at TIMESTAMPTZ DEFAULT now()
);

-- Index for session-based queries
CREATE INDEX idx_gfx_hands_session_id ON gfx_hands(session_id);

-- Index for recent hands (dashboard, monitoring)
CREATE INDEX idx_gfx_hands_created_at ON gfx_hands(created_at DESC);

-- Index for hand lookup by hand_id
CREATE INDEX idx_gfx_hands_hand_id ON gfx_hands(hand_id);

-- Comment for documentation
COMMENT ON TABLE gfx_hands IS 'Individual poker hands extracted from PokerGFX sessions. Supports incremental sync on file modifications.';
COMMENT ON COLUMN gfx_hands.hand_id IS 'Unique hand identifier from PokerGFX. Used for duplicate detection on file modifications.';
COMMENT ON COLUMN gfx_hands.hand_data IS 'Complete hand JSON including players, actions, and results.';
