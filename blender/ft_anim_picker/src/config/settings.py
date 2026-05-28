"""
Application Configuration
Centralized configuration for application settings
"""

import os
from pathlib import Path

# ============================================================================
# Application Settings
# ============================================================================
APP_NAME = "BGEN Asset Library"
APP_VERSION = "3.0.0"

# Default download location
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "BGEN Assets"

# Picker Templates
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "picker_templates"

# BPicker Library
DEFAULT_LIBRARY_PATH = Path.home() / "Documents" / "BGEN_Picker" / "Library"
LEGACY_LIBRARY_PATH = Path.home() / "Documents" / "FT_Anim_Picker" / "Library"
BPICKER_EXTENSION = ".bpicker"
LIBRARY_INDEX_NAME = "library_index.json"
BPICKER_MANIFEST_VERSION = 1

# UI Settings
WINDOW_MIN_WIDTH = 300
WINDOW_MIN_HEIGHT = 300
ASSET_GRID_MAX_COLS = 5
CARD_SIZE = 84
THUMBNAIL_SIZE = CARD_SIZE - (CARD_SIZE * 0.1)
PAGE_SEGMENT_CONTROL_SIZE = 18

# Download settings
DOWNLOAD_CHUNK_SIZE = 8192  # bytes

# FONT SETTINGS
FONT_SIZE_SMALL = 12
FONT_SIZE_MEDIUM = 14
FONT_SIZE_LARGE = 16

# External URLs
GITHUB_URL = "https://github.com/munorr/ft_anim_picker"
GITHUB_ISSUES_URL = "https://github.com/munorr/ft_anim_picker/issues"
WEBSITE_URL = "https://m2ky.com"
DISCORD_URL = "https://discord.com/channels/588508392960557057/1381941736049348759"
INSTAGRAM_URL = "https://www.instagram.com/m2ky.inc/"
YOUTUBE_URL = "https://www.youtube.com/playlist?list=PL-eygTHFskT0wYu47ZH07bQxmmenj7Ofw"
AUTHOR_NAME = "M2KY inc."

# ============================================================================
# Supabase Auth
# ============================================================================
SUPABASE_URL = "https://bdolptrvawlzfntyvjdl.supabase.co"          # Project URL, e.g. "https://xxxxx.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJkb2xwdHJ2YXdsemZudHl2amRsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIzMTI3NzAsImV4cCI6MjA4Nzg4ODc3MH0.xaXES5cn7FxBLp9-fNBTOwsezsj3wCUdTgWz6TgBqYU"     # Public anon key (safe to embed — RLS protects data)
AUTH_PREFS_FILE = "auth_prefs.json"
TOKEN_REFRESH_MARGIN = 300  # Refresh 5 min before expiry (seconds)

# Google OAuth — Supabase redirect captures the token via fragment
GOOGLE_OAUTH_REDIRECT = f"{SUPABASE_URL}/auth/v1/callback"
OAUTH_LOCAL_PORT = 8457  # Localhost port for capturing OAuth callback tokens
OAUTH_POLL_INTERVAL = 2000  # ms between session polls after OAuth redirect
OAUTH_POLL_TIMEOUT = 120000  # ms total timeout for OAuth polling

# Session heartbeat — how often to update last_active_at on user_sessions
SESSION_HEARTBEAT_INTERVAL = 1800000  # 30 minutes in milliseconds

# ============================================================================
# Library
# ============================================================================
LIBRARY_CARD_SIZE = CARD_SIZE  # Reuse standard card size

# Cache TTLs (seconds)
LIBRARY_CACHE_TTL = 300              # 5 min — products + sections
ENTITLEMENT_CACHE_TTL = 60           # 1 min — ownership checks
FEATURE_FLAG_CACHE_TTL = 3600        # 1 hour — feature flags
THUMBNAIL_CACHE_TTL = 86400          # 24 hours — thumbnail images

# Disk cache file names
LIBRARY_CACHE_FILE = "library_cache.json"
LIBRARY_THUMBNAIL_DIR = "thumbnail_cache"

# Stripe (publishable key is safe to embed — it's public by design)
STRIPE_PUBLISHABLE_KEY = "pk_test_51TAGL4DSiGc0QgCUGGz0adoM6c3B6dYK712Wx1545sHZjuP42uOFfcUzgIuE4dAELTDEKPHi8Djl31bVbVCYinTz009AHMPOvy"

# Library WebView — hosted web app URL (set when deployed)
LIBRARY_WEB_URL = "https://bgen-library-web.vercel.app"

# Storage bucket names
LIBRARY_THUMBNAILS_BUCKET = "library-thumbnails"

# Feature flag keys (match library_feature_flags table)
FF_LIBRARY_ENABLED = "library_enabled"
FF_LIBRARY_MIN_VERSION = "library_min_version"
FF_LIBRARY_REQUIRE_AUTH = "library_require_auth"  # Purchase gating (handled in code)
FF_LIBRARY_BROWSE_AUTH = "library_browse_auth"    # Browse gating (blocks non-signed-in users)

# ============================================================================
# Creator Profiles
# ============================================================================
CREATOR_CACHE_TTL = 300              # 5 min — creator list cache
CREATOR_AVATAR_SIZE = 48             # pixels — default for catalogue cards
CREATOR_STRIP_AVATAR_SIZE = 56       # pixels — avatar in explore strip
CREATOR_PROFILE_AVATAR_SIZE = 80     # pixels — avatar on profile page
CREATOR_BANNER_HEIGHT = 120        # pixels — profile page hero banner
DEFAULT_PAYOUT_SPLIT = 80            # Creator gets 80%, platform 20%
MIN_PAYOUT_CENTS = 2500              # $25 minimum payout threshold
CREATOR_ASSETS_BUCKET = "creator-assets"

# ============================================================================
# Update System
# ============================================================================
UPDATE_CHECK_TTL = 3600                          # 1 hour between version checks (seconds)
UPDATE_CACHE_FILE = "update_cache.json"          # disk cache for latest release info
UPDATE_CHANNEL = "stable"                        # default channel
UPDATE_CHANNELS = ["stable", "beta"]             # available channels
UPDATE_STORAGE_BUCKET = "addon-releases"         # Supabase Storage bucket name
UPDATE_PLATFORM = "blender"                      # platform identifier sent to backend

# Feature flag keys for update system
FF_UPDATE_SYSTEM_ENABLED = "update_system_enabled"
FF_UPDATE_BETA_VISIBLE = "update_beta_visible"

