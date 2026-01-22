-- SRS Scheduling Database Schema
-- Tracks spaced repetition schedule for vault notes

CREATE TABLE IF NOT EXISTS srs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path TEXT UNIQUE NOT NULL,
    note_type TEXT NOT NULL, -- 'idea', 'trail', 'moc', 'other'
    title TEXT NOT NULL,

    -- SRS metadata (synced from vault frontmatter)
    srs_enabled BOOLEAN DEFAULT TRUE,
    next_review_date DATE NOT NULL,
    last_review_date DATE,
    interval_days INTEGER DEFAULT 1,
    ease_factor REAL DEFAULT 2.5,
    repetitions INTEGER DEFAULT 0,

    -- Scheduling state
    is_due BOOLEAN DEFAULT FALSE,
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Stats
    total_reviews INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficient due card queries
CREATE INDEX IF NOT EXISTS idx_next_review
ON srs_cards(next_review_date, is_due, srs_enabled);

-- Index for note type filtering
CREATE INDEX IF NOT EXISTS idx_note_type
ON srs_cards(note_type);

-- Review history for analytics
CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rating INTEGER NOT NULL, -- 0=Again, 1=Hard, 2=Good, 3=Easy
    interval_before INTEGER,
    interval_after INTEGER,
    ease_factor_before REAL,
    ease_factor_after REAL,

    FOREIGN KEY (card_id) REFERENCES srs_cards(id) ON DELETE CASCADE
);

-- Config table for system settings
CREATE TABLE IF NOT EXISTS srs_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default config values
INSERT OR IGNORE INTO srs_config (key, value) VALUES
    ('morning_batch_time', '09:00'),
    ('morning_batch_size', '5'),
    ('telegram_chat_id', ''),
    ('last_batch_sent', ''),
    ('vault_path', '/Users/server/Research/vault');
