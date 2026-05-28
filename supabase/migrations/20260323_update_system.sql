-- ============================================================================
-- Addon Update System
-- Tables for managing addon releases and tracking update events/analytics.
-- ============================================================================

-- addon_releases: stores every published (or draft) addon version
CREATE TABLE IF NOT EXISTS addon_releases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         TEXT NOT NULL UNIQUE,                          -- e.g. "3.1.0"
    channel         TEXT NOT NULL DEFAULT 'stable',                -- 'stable' | 'beta'
    min_update_version TEXT,                                       -- minimum client version allowed to update to this

    -- Storage paths inside the private "addon-releases" bucket
    storage_path_blender TEXT,                                     -- e.g. "releases/3.1.0/blender_bgen_picker.zip"
    storage_path_maya    TEXT,

    -- Integrity / size
    file_hash_blender TEXT,                                        -- SHA-256 hex digest
    file_hash_maya    TEXT,
    file_size_blender BIGINT DEFAULT 0,
    file_size_maya    BIGINT DEFAULT 0,

    -- Content
    changelog     TEXT,                                            -- Markdown, shown to users
    release_notes TEXT,                                            -- Short user-facing summary
    dev_notes     TEXT,                                            -- Internal only (never sent to clients)

    -- Publishing controls
    is_published     BOOLEAN   DEFAULT false,
    rollout_percent  INTEGER   DEFAULT 100 CHECK (rollout_percent BETWEEN 0 AND 100),
    is_critical      BOOLEAN   DEFAULT false,                      -- red banner, cannot dismiss

    created_at   TIMESTAMPTZ DEFAULT now(),
    published_at TIMESTAMPTZ
);

-- Index for the most common query: latest published release per channel
CREATE INDEX IF NOT EXISTS idx_addon_releases_published
    ON addon_releases (channel, is_published, version DESC)
    WHERE is_published = true;


-- addon_update_events: analytics for update checks, downloads, completions, failures
CREATE TABLE IF NOT EXISTS addon_update_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID,                                            -- NULL for anonymous users
    from_version  TEXT NOT NULL,
    to_version    TEXT NOT NULL,
    platform      TEXT NOT NULL,                                   -- 'blender' | 'maya'
    host_version  TEXT,                                            -- e.g. "Blender 4.2", "Maya 2025"
    os_info       TEXT,                                            -- e.g. "Darwin 25.3.0"
    event_type    TEXT NOT NULL,                                   -- 'check' | 'download_start' | 'download_complete' | 'download_fail'
    error_message TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Index for querying events by version and type
CREATE INDEX IF NOT EXISTS idx_addon_update_events_version
    ON addon_update_events (to_version, event_type, created_at DESC);


-- ============================================================================
-- Row Level Security
-- ============================================================================

ALTER TABLE addon_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE addon_update_events ENABLE ROW LEVEL SECURITY;

-- addon_releases: anyone can read published releases (anon key)
CREATE POLICY "Public can read published releases"
    ON addon_releases FOR SELECT
    USING (is_published = true);

-- addon_update_events: anyone can insert (anonymous analytics)
CREATE POLICY "Anyone can insert update events"
    ON addon_update_events FOR INSERT
    WITH CHECK (true);

-- addon_update_events: only service role can read (dashboard queries)
-- (No SELECT policy for anon/authenticated = denied by default with RLS enabled)
