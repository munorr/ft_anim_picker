-- ============================================================================
-- Aggregate daily update checks
-- Replaces per-check rows in addon_update_events with a single row per
-- (date, platform, host, os, version) combination, reducing volume ~24x.
-- ============================================================================

CREATE TABLE IF NOT EXISTS addon_daily_checks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_date    DATE NOT NULL,
    platform      TEXT NOT NULL,
    host_version  TEXT NOT NULL,
    os_info       TEXT NOT NULL,
    from_version  TEXT NOT NULL,
    check_count   INTEGER NOT NULL DEFAULT 1,
    last_check_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (check_date, platform, host_version, os_info, from_version)
);

CREATE INDEX IF NOT EXISTS idx_addon_daily_checks_date_platform
    ON addon_daily_checks (check_date, platform);

-- RLS: service-role key is used by Edge Functions (bypasses RLS),
-- but enable it so anon/authenticated cannot read analytics.
ALTER TABLE addon_daily_checks ENABLE ROW LEVEL SECURITY;

-- Atomic upsert function: insert or increment check_count
CREATE OR REPLACE FUNCTION upsert_daily_check(
    p_date DATE,
    p_platform TEXT,
    p_host TEXT,
    p_os TEXT,
    p_version TEXT
) RETURNS void AS $$
BEGIN
    INSERT INTO addon_daily_checks (check_date, platform, host_version, os_info, from_version)
    VALUES (p_date, p_platform, p_host, p_os, p_version)
    ON CONFLICT (check_date, platform, host_version, os_info, from_version)
    DO UPDATE SET check_count   = addon_daily_checks.check_count + 1,
                  last_check_at = now();
END;
$$ LANGUAGE plpgsql;
