# BGEN Marketplace — Remote Hosting, CMS, & Full Integration Plan

> Companion to [BGEN_ACCOUNT_SYSTEM_PLAN.md](BGEN_ACCOUNT_SYSTEM_PLAN.md) which covers Auth, DB schema, and Purchase flow foundations.

## Context
The Explore page UI is built (HeroCarousel, SectionRows, Collections, CreatorSpotlight — all wired to mock data in `marketplace_manager.py`). Now we need to:
1. **Host the Explore page data remotely** so sections/products can be updated without a tool release
2. **Define a CMS workflow** for creating/editing products, collections, and sections
3. **Build the full integration pipeline**: marketplace → purchase → download → library

---

## 1. Remote Data Architecture

### Strategy: Single Edge Function for Explore Layout

Instead of the client making N+1 PostgREST queries to resolve sections and products, a single Edge Function (`fetch-explore-layout`) returns the **entire Explore page** in one call. This is the key architectural decision — it means:
- The Explore page layout is 100% server-controlled (change sections without a tool update)
- Section scheduling (starts_at / expires_at) is evaluated server-side
- Product resolution (algorithmic sorting, collection expansion) happens server-side
- Thumbnail URLs are constructed server-side (public bucket, no signing needed)
- Feature flags are bundled in the same response

### Supabase Tables

#### `marketplace_sections` — Explore Page Layout
```sql
CREATE TABLE marketplace_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,               -- "hero", "new-this-week", "trending"
    type TEXT NOT NULL,                      -- "hero" | "algorithmic" | "creator_spotlight" | "collection_grid"
    title TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    slides JSONB DEFAULT '[]'::jsonb,        -- Hero: [{product_id, headline, subtitle, cta_text, accent_color}]
    algorithm JSONB DEFAULT '{}'::jsonb,     -- Algorithmic: {sort, limit, filter}
    creator_name TEXT,                       -- Spotlight: creator display name
    product_ids UUID[] DEFAULT '{}',         -- Spotlight: explicit product list
    collections JSONB DEFAULT '[]'::jsonb,   -- Collection grid: [{name, slug, accent, product_ids[]}]
    is_active BOOLEAN DEFAULT true,
    starts_at TIMESTAMPTZ,                   -- NULL = immediately active
    expires_at TIMESTAMPTZ,                  -- NULL = never expires
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE marketplace_sections ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anyone can read active sections" ON marketplace_sections FOR SELECT
    USING (is_active AND (starts_at IS NULL OR starts_at <= now()) AND (expires_at IS NULL OR expires_at > now()));
```

#### `marketplace_products` — Product Catalog (from existing plan, unchanged)
Already defined in `BGEN_ACCOUNT_SYSTEM_PLAN.md`. Key fields: `id, slug, name, short_description, creator_id, price_cents, storage_path, thumbnail_path, status, featured, tags, rating_avg, download_count`.

RLS: Anyone can SELECT where `status = 'published'`. No INSERT/UPDATE for users.

#### `marketplace_purchases` — Entitlements (from existing plan, unchanged)
RLS: Users SELECT own. No INSERT for users (Edge Functions only via service_role).

#### `marketplace_feature_flags` — Remote Kill Switches
```sql
CREATE TABLE marketplace_feature_flags (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT 'true'::jsonb,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Seed:
INSERT INTO marketplace_feature_flags (key, value, description) VALUES
    ('marketplace_enabled', 'true', 'Master on/off switch'),
    ('marketplace_require_auth', 'true', 'Require sign-in for purchases'),
    ('marketplace_min_version', '"2.3.0"', 'Minimum addon version');
```

### Storage Buckets

| Bucket | Access | Contents |
|--------|--------|----------|
| `marketplace-thumbnails` | **Public** | `{product_id}/thumb.png`, `{product_id}/preview_N.png` |

Thumbnails are public on Supabase Storage. Product files (.bpicker) are hosted on Polar.sh via the File Downloads benefit — no Supabase Storage bucket needed for assets.

---

## 2. Edge Functions

| Function | Auth | Purpose |
|----------|------|---------|
| `fetch-explore-layout` | anon or token | Returns full Explore page: resolved sections + products + feature flags in one call |
| `check-entitlements` | token required | Bulk ownership check for product_ids → returns owned set |
| `create-checkout` | token required | Creates Polar checkout session, returns checkout URL |
| `polar-webhook` | Standard Webhooks signature | Webhook handler: verifies signature, creates purchase record on `order.paid` |
| `generate-download-url` | token required | Verifies entitlement → queries Polar Customer State API for File Downloads URL |

### `fetch-explore-layout` — Critical Path
```
Request:  POST /functions/v1/fetch-explore-layout  { }
Response: {
  "sections": [
    { "slug": "hero", "type": "hero", "slides": [{...product data + thumbnail URLs}] },
    { "slug": "trending", "type": "algorithmic", "title": "Trending", "products": [{...}] },
    ...
  ],
  "feature_flags": { "marketplace_enabled": true, "marketplace_min_version": "2.3.0" }
}
```

Server logic:
1. Query `marketplace_sections` (active + within schedule window), ordered by `position`
2. For each section type, resolve products from `marketplace_products`
3. Construct public thumbnail URLs: `{SUPABASE_URL}/storage/v1/object/public/marketplace-thumbnails/{id}/thumb.png`
4. Bundle feature flags from `marketplace_feature_flags`
5. Return everything in one response

---

## 3. Caching Architecture

### Two-Tier: Memory + Disk

```
Request → Memory cache (fresh?) → YES → serve immediately
                                → NO  → Network fetch → success → update memory + disk → serve
                                                       → fail   → Disk cache (stale?) → YES → serve with "offline" banner
                                                                                       → NO  → Mock data fallback
```

**Memory** (in `MarketplaceManager`):
- `_products_cache`, `_sections_cache`, `_owned_ids`, `_feature_flags` + timestamps

**Disk** (`marketplace_cache.json` alongside `auth_prefs.json`):
- Written on every successful fetch, loaded on startup
- Survives addon restarts without re-fetching

**Thumbnail disk cache** (`thumbnail_cache/{product_id}.png`):
- Downloaded once, checked by file age

### TTL Values (new constants in `config/settings.py`)
```python
MARKETPLACE_CACHE_TTL = 300          # 5 min — products + sections
ENTITLEMENT_CACHE_TTL = 60           # 1 min — ownership checks
FEATURE_FLAG_CACHE_TTL = 3600        # 1 hour — feature flags
THUMBNAIL_CACHE_TTL = 86400          # 24 hours — thumbnail images
MARKETPLACE_CACHE_FILE = "marketplace_cache.json"
MARKETPLACE_THUMBNAIL_DIR = "thumbnail_cache"
PURCHASE_POLL_INTERVAL = 3000        # 3s polling during checkout
PURCHASE_POLL_TIMEOUT = 120000       # 2 min max wait
MARKETPLACE_THUMBNAILS_BUCKET = "marketplace-thumbnails"
# Product files (.bpicker) hosted on Polar.sh via File Downloads benefit
```

---

## 4. Access Control Strategy

### Tiered Visibility (browse free, pay to download)

| Feature | Auth Required? | Mechanism |
|---------|---------------|-----------|
| See BGEN Library tab | No | Always visible (drives discovery) |
| Browse Explore page | No | Public `marketplace_products` + `marketplace_sections` SELECT |
| View product details | No | Same |
| See thumbnails | No | Public Storage bucket |
| Buy / Get Free | **Yes** | Auth check in `blender_ui._on_bgen_product_action()` |
| Download owned product | **Yes** | Edge Function verifies JWT + purchase record |
| See "Owned" badges | **Yes** | `check-entitlements` requires auth |

When an unauthenticated user clicks "Buy" or "Get Free":
→ Navigate to Settings > Account page with a "Sign in to continue" message

### Feature Flag Gating
```python
def _should_show_marketplace(self):
    flags = self._feature_flags
    if not flags.get("marketplace_enabled", True):
        return False
    min_ver = flags.get("marketplace_min_version", "0.0.0")
    return version_gte(CFG.APP_VERSION, min_ver)
```
- Checked in `blender_ui._on_library_tab_changed()` before showing BGEN Library
- If disabled: show "Marketplace coming soon" or "Please update" banner

---

## 5. CMS / Admin Workflow

### Solo Developer Approach: Supabase Dashboard + Python Scripts

No custom admin panel. The Supabase Table Editor is the CMS.

### Product Lifecycle
```
draft → published → unlisted → archived
```

### New Product Pipeline
1. Create `.bpicker` locally using the addon
2. Run `scripts/admin_upload_product.py`:
   - Reads .bpicker metadata (UUID, name, author)
   - Uploads thumbnail → `marketplace-thumbnails/{id}/thumb.png` (public Supabase Storage)
   - Creates Polar product with File Downloads benefit, uploads .bpicker file
   - Inserts row in `marketplace_products` with `status='draft'`, `polar_product_id`, `polar_benefit_id`
3. Review in Supabase Dashboard Table Editor
4. Set `status = 'published'` → live within 5 minutes (cache TTL)

### Section Management
- Edit `marketplace_sections` rows directly in Supabase Dashboard
- Change hero slides, collection contents, algorithmic params via JSON fields
- Set `starts_at`/`expires_at` for time-limited promotions
- Changes propagate to all users within `MARKETPLACE_CACHE_TTL` (5 min)

### Collection Management
- Collections are defined inline in `marketplace_sections` (type `collection_grid`, `collections` JSONB field)
- Each collection: `{name, slug, accent, product_ids[]}`
- Edit product_ids array in Dashboard to add/remove/reorder products

### Admin Scripts (local tools, use service_role key)
```
scripts/
  admin_upload_product.py      -- Upload .bpicker + thumbnail, create product row
  admin_update_product.py      -- Swap .bpicker file, update metadata
  admin_manage_sections.py     -- Export/import section definitions as JSON
```

---

## 6. MarketplaceManager — Real Methods

### New Worker Pattern (mirrors `_AuthWorker` from `auth_manager.py`)
```python
class _MarketplaceWorker(QThread):
    finished = Signal(object)
    error = Signal(str)
    def __init__(self, fn, *args): ...
    def run(self): ...
```

### New Signals
```python
sections_loaded = Signal(list)              # Resolved section dicts
entitlements_checked = Signal(set)          # Owned product IDs
download_started = Signal(str)              # product_id
download_progress = Signal(str, int, int)   # product_id, bytes_done, total
download_completed = Signal(str, str)       # product_id, library_path
download_failed = Signal(str, str)          # product_id, error
feature_flags_loaded = Signal(dict)
```

### Key Methods
```python
# Async fetchers (background thread → signal on completion)
def fetch_catalog(self, force=False)          # query marketplace_products
def fetch_explore_sections(self, force=False) # invoke fetch-explore-layout
def fetch_feature_flags(self)                 # query marketplace_feature_flags
def check_entitlements(self, product_ids)     # invoke check-entitlements

# Synchronous (serve from memory cache)
def get_products(...) -> list                 # filter/sort cached products
def get_explore_sections() -> list            # return cached sections
def is_owned(product_id) -> bool              # check cached owned set

# Purchase flow
def initiate_purchase(self, product_id)       # create-checkout → browser → poll
def download_product(self, product_id)        # generate-download-url → stream → library

# Thumbnails
def get_thumbnail_url(self, product) -> str   # public bucket URL construction
def load_thumbnail_async(self, product_id, url, callback)  # background download
```

### Dual-Mode Fallback
All `get_*` methods check: memory cache → disk cache → mock data. The mock functions (`_mock_products()`, `_mock_sections()`) remain as the ultimate offline fallback.

---

## 7. Full Integration Pipeline

### Download Flow
```
User clicks "Download" on owned product
  → MarketplaceManager.download_product(product_id)
    → _MarketplaceWorker:
      1. invoke("generate-download-url", token, {product_id})  → signed_url
      2. download_file(signed_url, temp_path, progress_callback)
      3. Validate: zipfile.is_zipfile() + BPickerArchive basic check
      4. LibraryManager.add_to_library(temp_path, overwrite=True)
         → LibraryManager.notify_watchers()  → library grid auto-refreshes
      5. Clean up temp file
    → download_completed signal
```

### Purchase Flow
```
User clicks "Buy $4.99"
  → Auth check (if not signed in → navigate to Account page)
  → MarketplaceManager.initiate_purchase(product_id)
    → invoke("create-checkout", token, {product_id})  → checkout_url
    → webbrowser.open(checkout_url)
    → QTimer polls marketplace_purchases every 3s (max 2 min)
    → Purchase found → purchase_completed signal
    → Auto-trigger download_product(product_id)
```

### Thumbnail Loading
```
MarketplaceCard.__init__:
  1. Set default icon (initials, current behavior)
  2. Check thumbnail_cache/{product_id}.png on disk
     → If fresh: load QPixmap, set on _thumb_label
     → If stale/missing: MarketplaceManager.load_thumbnail_async(...)
       → Background: download from public bucket URL
       → Callback on main thread: card._thumb_label.setPixmap(pixmap)
```

### Existing Code That Does NOT Change
- `library_manager.py` — `add_to_library()` already handles the import
- `bpicker_format.py` — `BPickerArchive.validate()` used for post-download checks
- `picker_session.py` — Downloaded .bpicker opens via normal library flow
- `supabase_client.py` — `query()`, `invoke()`, `download_file()` already sufficient
- `library_ui.py` — `LibraryManager.notify_watchers()` triggers grid refresh automatically

---

## 8. Files to Modify

| File | Changes |
|------|---------|
| `src/marketplace_manager.py` | Replace mock methods with real Supabase calls. Add `_MarketplaceWorker`, cache infrastructure (memory + disk), `fetch_catalog()`, `fetch_explore_sections()`, `check_entitlements()`, `initiate_purchase()`, `download_product()`, `load_thumbnail_async()`, feature flag checking. Keep mock data as fallback. |
| `src/marketplace_ui.py` | Add async thumbnail loading in `MarketplaceCard`, `SectionRowWidget`, `ProductDetailPage`. Add loading skeleton states. Add error/offline banners. |
| `src/blender_ui.py` | Replace `simulate_purchase`/`simulate_download` with real methods. Wire `feature_flags_loaded` for marketplace gating. Wire `download_progress`/`download_completed` signals. Add auth check before purchase. |
| `src/config/settings.py` | Add cache TTL constants, bucket names, polling intervals. |

### New Files (Server-Side, Not in Addon)
```
supabase/functions/fetch-explore-layout/index.ts
supabase/functions/check-entitlements/index.ts
supabase/functions/create-checkout/index.ts
supabase/functions/polar-webhook/index.ts
supabase/functions/generate-download-url/index.ts
scripts/admin_upload_product.py
scripts/admin_manage_sections.py
```

---

## 9. Implementation Order

| Step | Phase | What |
|------|-------|------|
| 1 | Backend | Create Supabase tables (sections, feature_flags) + Storage buckets |
| 2 | Backend | Seed `marketplace_sections` with current mock section data |
| 3 | Backend | Seed `marketplace_products` with current mock product data |
| 4 | Backend | Deploy `fetch-explore-layout` Edge Function |
| 5 | Backend | Deploy `check-entitlements` Edge Function |
| 6 | Client | Add new constants to `config/settings.py` |
| 7 | Client | Add `_MarketplaceWorker` + cache infrastructure to `marketplace_manager.py` |
| 8 | Client | Implement `fetch_catalog()` + `fetch_explore_sections()` + `fetch_feature_flags()` |
| 9 | Client | Wire `sections_loaded` → `ExplorePageWidget._force_refresh()` |
| 10 | Client | Implement `check_entitlements()` + wire to card "Owned" badges |
| 11 | Client | Add thumbnail loading pipeline (public URL → disk cache → QPixmap callback) |
| 12 | Client | Wire feature flag gating in `blender_ui.py` |
| 13 | Backend | Deploy `generate-download-url` Edge Function |
| 14 | Client | Implement `download_product()` flow |
| 15 | Backend | Set up Polar.sh products + deploy `create-checkout` + `polar-webhook` |
| 16 | Client | Implement `initiate_purchase()` flow (checkout → poll → download) |
| 17 | Client | Replace simulate_* calls in `blender_ui.py` with real methods |
| 18 | Polish | Add loading skeletons, error banners, retry logic, progress indicators |
| 19 | Admin | Create `admin_upload_product.py` and `admin_manage_sections.py` scripts |
| 20 | Test | End-to-end: browse → buy (Polar sandbox) → webhook → download → open in library |

---

## 10. Verification

1. **Remote sections**: Change a section title in Supabase Dashboard → wait 5 min → Explore page shows new title
2. **Feature flag kill switch**: Set `marketplace_enabled = false` → BGEN Library tab shows "coming soon" banner
3. **Offline fallback**: Disconnect network → Explore page renders from disk cache or mock data
4. **Auth gating**: Click "Buy" while signed out → navigates to Account page
5. **Purchase**: Complete Polar sandbox checkout → purchase_completed signal → auto-download → .bpicker appears in My Library
6. **Thumbnail loading**: Cards show initials initially → thumbnails load asynchronously from public bucket
7. **Entitlements**: Purchased product shows "Owned" badge on all cards
