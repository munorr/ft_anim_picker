# BGEN Account & Marketplace System — Architecture Plan

## Context

The BGEN account system (Supabase email-OTP auth) is **fully implemented** and working. The local `.bpicker` library system is also complete. The next major milestone is building a **marketplace** within the addon where users can browse, purchase, and download picker assets — and eventually allow other creators to sell their work.

The solo-developer constraint demands: managed third-party providers, zero PCI scope, zero new Python dependencies, and maximum security delegation to trusted services.

---

## Recommended Stack

| Layer | Provider | Why |
|---|---|---|
| **Auth** | Supabase (OTP done, + Google OAuth) | Email-OTP working + add Google OAuth for one-click sign-in |
| **Database** | Supabase PostgREST (already done) | Direct queries with RLS, zero deps |
| **Payments** | **Polar.sh** (Merchant of Record) | See justification below |
| **Asset Storage** | Polar File Downloads (assets) + Supabase Storage (thumbnails) | Polar handles signed URLs for purchased files |
| **Serverless Backend** | Supabase Edge Functions | Webhook handling, checkout creation |
| **Checkout UX** | Browser redirect to Polar checkout | Simple, consistent flow |

### Why Polar.sh over Stripe / LemonSqueezy

| Factor | Polar.sh | Stripe | LemonSqueezy |
|---|---|---|---|
| Tax/VAT handling | **Fully handled** (MoR) | You manage | Fully handled (MoR) |
| Refund disputes | **Polar handles** | You handle | LS handles |
| PCI burden | None | None (hosted) | None |
| Legal entity needed | No (MoR) | Yes | No (MoR) |
| Fee | **4% + $0.40** | 2.9% + $0.30 | 5% + $0.50 |
| `external_customer_id` | **Yes** (maps to Supabase user_id) | Via metadata | Via custom data |
| File delivery | **Built-in** (10GB, signed URLs) | Manual | Manual |
| Open source | **Yes** (Apache 2.0) | No | No |
| Solo dev verdict | **Best choice** — lowest MoR fees, built-in file delivery, Supabase adapter | Better at scale | Higher fees, no file delivery |

Polar.sh acts as **Merchant of Record** — they are the legal seller, handle global sales tax/VAT, process refunds and chargebacks. You never touch card data or tax filings. Polar is built on top of Stripe.

---

## Auth: Add Google OAuth

### Why Google OAuth (not passwords or magic links)
- **One-click sign-in** — fastest auth method, no codes to copy
- **Studio-ready** — studios using Google Workspace already manage `artist@studio.com` accounts; provisioning/deprovisioning controls access automatically
- **No password liability** — no reset flow, no breach notifications, no strength rules
- **Magic link is redundant** with OTP (both require email)
- **Supabase built-in** — configuration change + UI button, minimal code

### Implementation (in `auth_manager.py`)
- Add `sign_in_with_google()` method that:
  1. Calls Supabase GoTrue `/auth/v1/authorize?provider=google` to get the OAuth URL
  2. Opens URL in browser via `webbrowser.open()`
  3. Supabase handles the OAuth callback via its built-in redirect
  4. Addon polls `/auth/v1/session` or uses a localhost callback to receive tokens
- Supabase setup: Enable Google provider in Supabase Dashboard > Auth > Providers, add Google Cloud OAuth client ID/secret

### UI Changes (in `settings_page.py` AccountSection)
- Add "Sign in with Google" button on the signed-out splash (state 0)
- Keep existing email-OTP flow as alternative
- Signed-in state shows email regardless of auth method

---

## Auth: Session & Account Switching Fixes

### Current Issues (in `auth_manager.py`)
1. **No clean sign-out on account switch** — `_on_session_received()` overwrites the old session without calling `sign_out()` first, orphaning the old `user_sessions` row and leaving the old token valid server-side
2. **No "sign out all devices"** — users can't invalidate all sessions if a device is compromised

### Fix 1: Auto sign-out before new sign-in
In `_on_session_received()` (line 234), before processing the new session:
```python
def _on_session_received(self, result: dict):
    # If already signed in as a different user, clean up the old session first
    if self._access_token:
        self._unregister_session()  # Remove old user_sessions row
        try:
            self._client.sign_out(self._access_token)  # Invalidate old token server-side
        except Exception:
            pass
        self._clear_session()
    # ... then process the new session as before
```
This ensures:
- Old `user_sessions` row is deleted
- Old access token is invalidated server-side
- Old local session state is cleared
- New session is stored cleanly

### Fix 2: Add `sign_out_all_devices()` method
```python
def sign_out_all_devices(self):
    """Sign out from all devices — invalidates all refresh tokens globally."""
    if not self._access_token or not self._user:
        return
    user_id = self._user.get("id", "")
    # 1. Delete ALL user_sessions rows for this user
    try:
        self._client.delete("user_sessions", self._access_token, f"user_id=eq.{user_id}")
    except Exception:
        pass
    # 2. Supabase global sign-out — invalidates ALL refresh tokens
    try:
        self._client.sign_out(self._access_token, scope="global")
    except Exception:
        pass
    # 3. Clear local session
    self._clear_session()
    self.auth_state_changed.emit(False)
```
Requires adding `scope` parameter to `supabase_client.py`'s `sign_out()` method.

### Fix 3: UI — "Sign out everywhere" button
Add to AccountSection signed-in state (state 3):
- Below the "Sign Out" button, add a smaller "Sign out all devices" link/button
- Shows confirmation dialog: "This will sign you out on all devices. Continue?"
- Calls `AuthManager.sign_out_all_devices()`

---

## Security Architecture

### Trust Boundaries

```
SERVER-SIDE (Edge Functions only — never exposed to client):
  ├── Supabase service_role key
  ├── Polar access token
  ├── Polar webhook signing secret
  ├── Purchase INSERT logic (prevents fake purchases)
  └── Polar Customer State API queries (gates downloads)

CLIENT-SIDE (safe to embed — RLS protects data):
  ├── Supabase anon key (already in config/settings.py)
  └── Supabase project URL
```

### Key Security Guarantees

1. **Purchases can only be created by the webhook Edge Function** — no INSERT RLS policy for users on `marketplace_purchases`
2. **Downloads gated by server-side entitlement check** — Edge Function verifies purchase via Polar Customer State API before returning download URL
3. **Webhook verified via Standard Webhooks spec** — HMAC-SHA256 signature with timestamp replay protection
4. **Polar provides signed download URLs** — files delivered via Polar's built-in File Downloads benefit
5. **Addon never sees card data** — all purchases go through Polar's hosted checkout page (built on Stripe)
6. **DRM-free files** — simpler, user-friendly; optional buyer UUID in metadata for accountability

---

## Database Schema (Supabase)

### `marketplace_products`
```sql
id UUID PRIMARY KEY
slug TEXT UNIQUE NOT NULL           -- "advanced-biped-picker"
name TEXT NOT NULL
description TEXT
short_description TEXT              -- One-liner for card
creator_id UUID → auth.users(id)
category TEXT DEFAULT 'picker'      -- 'picker', 'template', 'pose_pack'
tags TEXT[]
price_cents INTEGER DEFAULT 0      -- 0 = free
currency TEXT DEFAULT 'USD'
polar_product_id TEXT               -- Polar product ID
polar_benefit_id TEXT               -- Polar File Downloads benefit ID
thumbnail_path TEXT
preview_images TEXT[]
download_count INTEGER DEFAULT 0
rating_avg NUMERIC(3,2) DEFAULT 0
rating_count INTEGER DEFAULT 0
status TEXT DEFAULT 'draft'         -- 'published', 'unlisted', 'archived'
featured BOOLEAN DEFAULT false
```

### `user_profiles` (links Supabase auth to Polar customer)
```sql
user_id UUID PRIMARY KEY → auth.users(id)
email TEXT
display_name TEXT
polar_customer_id TEXT              -- Set by webhook on first purchase (optional reference)
created_at TIMESTAMPTZ DEFAULT now()
```

### `marketplace_purchases`
```sql
id UUID PRIMARY KEY
user_id UUID → auth.users(id) NOT NULL
product_id UUID → marketplace_products(id) NOT NULL
price_paid_cents INTEGER DEFAULT 0
polar_order_id TEXT
license_key TEXT
status TEXT DEFAULT 'completed'     -- 'refunded', 'disputed'
download_count INTEGER DEFAULT 0
UNIQUE(user_id, product_id)
```

### `marketplace_reviews` (Phase 3)
```sql
id UUID PRIMARY KEY
user_id UUID → auth.users(id)
product_id UUID → marketplace_products(id)
rating INTEGER CHECK (1-5)
comment TEXT
UNIQUE(user_id, product_id)
```

### `teams` (Studio/Organization — build later, schema now)
```sql
id UUID PRIMARY KEY
name TEXT NOT NULL                     -- "Pixar Animation"
slug TEXT UNIQUE                       -- "pixar-animation"
owner_id UUID → auth.users(id)        -- Billing owner
plan TEXT DEFAULT 'free'               -- 'free', 'team', 'studio' (future tiers)
max_seats INTEGER DEFAULT 5
polar_subscription_id TEXT             -- Team subscription (future)
storage_quota_bytes BIGINT DEFAULT 5368709120  -- 5GB default
storage_used_bytes BIGINT DEFAULT 0
created_at TIMESTAMPTZ DEFAULT now()
```

### `team_members`
```sql
id UUID PRIMARY KEY
team_id UUID → teams(id) NOT NULL
user_id UUID → auth.users(id) NOT NULL
role TEXT DEFAULT 'member'             -- 'owner', 'admin', 'member'
invited_by UUID → auth.users(id)
joined_at TIMESTAMPTZ DEFAULT now()
UNIQUE(team_id, user_id)
```

### `team_library` (shared cloud .bpicker pool)
```sql
id UUID PRIMARY KEY
team_id UUID → teams(id) NOT NULL
product_id UUID → marketplace_products(id)  -- NULL if uploaded, not purchased
uploaded_by UUID → auth.users(id)
bpicker_storage_path TEXT NOT NULL     -- Supabase Storage path
name TEXT NOT NULL
metadata JSONB DEFAULT '{}'
created_at TIMESTAMPTZ DEFAULT now()
```

### How Teams Work (Future Implementation)
- **Team purchases**: Owner buys a product → entitlement shared with all team members (via `team_id` on purchase or team_library)
- **Cloud library**: Team members upload .bpicker files to shared Supabase Storage bucket, scoped by `team_id`
- **Access control**: RLS checks `team_members` to verify user belongs to team before granting access
- **Studio Google Workspace**: IT manages `@studio.com` Google accounts → OAuth sign-in → auto-join team by email domain (future Edge Function)

### Design Decision: Team-Aware Purchases
The `marketplace_purchases` table is currently `user_id` scoped. For team purchases, two options:
- **Option A**: Add `team_id` column to `marketplace_purchases` — team members query by team_id
- **Option B**: Separate `team_purchases` table — cleaner separation, no migration of individual purchases
- **Chosen**: Option A (add nullable `team_id`) — simpler, one table to check for entitlements

### Updated `marketplace_purchases` (with team support)
```sql
id UUID PRIMARY KEY
user_id UUID → auth.users(id) NOT NULL
product_id UUID → marketplace_products(id) NOT NULL
team_id UUID → teams(id)              -- NULL for individual purchases
price_paid_cents INTEGER DEFAULT 0
polar_order_id TEXT
license_key TEXT
status TEXT DEFAULT 'completed'
download_count INTEGER DEFAULT 0
UNIQUE(user_id, product_id)           -- Individual uniqueness
-- Team purchases: one per team per product (enforced by Edge Function)
```

### RLS Policies
- **Products**: Anyone can SELECT where `status = 'published'`; creators can manage their own
- **Purchases**: Users can SELECT their own OR purchases with matching `team_id` (via team_members lookup); **NO INSERT for users** (Edge Function only)
- **Reviews**: Anyone can read published; users can write/edit their own
- **Teams**: Members can SELECT their team; owner/admin can UPDATE
- **Team members**: Members can see their own team's roster; owner/admin can INSERT/DELETE
- **Team library**: Members can SELECT/INSERT for their team; owner/admin can DELETE

---

## Supabase Edge Functions

| Function | Purpose |
|---|---|
| `create-checkout` | Creates Polar checkout session with `external_customer_id` = Supabase user_id, returns checkout URL |
| `polar-webhook` | Verifies Standard Webhooks signature, handles `order.paid` event, inserts purchase record |
| `generate-download-url` | Verifies entitlement, queries Polar Customer State API for File Downloads benefit URL |
| `check-entitlements` | Bulk ownership check for a list of product IDs (payment-provider-agnostic) |
| `fetch-explore-layout` | Returns full Explore page layout with sections and products |

---

## Purchase Flow (User Experience)

### Paid Purchase (browser checkout)
```
Click "Buy $X.XX"
  → Addon calls create-checkout Edge Function
  → Edge Function creates Polar checkout session (external_customer_id = Supabase user_id)
  → Addon opens checkout URL in default browser (webbrowser.open)
  → User enters payment info on Polar's hosted checkout page (built on Stripe)
  → Polar processes payment → POSTs order.paid webhook
  → polar-webhook Edge Function verifies Standard Webhooks signature
  → Edge Function inserts purchase record + stores polar_customer_id
  → Addon polls marketplace_purchases every 3s (up to 2 min)
  → Purchase appears → auto-download begins
```
Note: Returning customers see pre-filled checkout details via `external_customer_id`.

### Free Items (sign-in required)
```
Click "Download" (free item)
  → If not signed in → navigate to Settings > Account
  → If signed in → Edge Function creates purchase record (price=0) + returns success
  → Download begins immediately
```

### Payment Management
- Polar provides a Customer Portal where users can view orders, manage subscriptions, and access benefits
- No payment data ever stored in the addon

---

## BGEN Library UI Design (from screenshots + user input)

### Tab Structure
The Library page (`library_stack` QStackedWidget, index 0/1) has two sub-pages:
- **My Library** (index 0) — Local .bpicker files, managed by `LibraryPageController`
- **BGEN Library** (index 1) — Marketplace, has two sub-views toggled by left icons

### BGEN Library Sub-Views

**Explore (curated storefront):**
- Activated by the left circle/compass icon
- Beautiful showcase page with featured items, curated collections, animations
- Think "app store featured" — hero banners, category spotlights, "new this week"
- Purpose: Discovery, browsing inspiration, highlighting premium content

**Catalogue (grid browse):**
- Activated by the list icon
- Standard grid of `MarketplaceCard` widgets (same pattern as My Library)
- Filtered by Category dropdown ("Picker" etc.) + search + filter controls
- Purpose: Efficient browsing when user knows what they want

### BGEN Library Toolbar
```
[Explore icon] [Catalogue icon]  |  Category ▾ Picker  |  [Filter] [Search]
```
- No "+" button (users don't add to BGEN Library, they download from it)
- Category dropdown filters catalogue view
- Search searches by name/tags/creator
- Filter icon opens advanced filters (price range, rating, free/paid)

### MarketplaceCard Widget (extends PickerCard pattern)
Same visual style as `PickerCard` in `library_ui.py`:
```
MarketplaceCard (QFrame)
└── QVBoxLayout (margins: 4,4,4,2 | spacing: 2)
    ├── QLabel (thumbnail, same sizing as PickerCard._thumb_size)
    │   └── "Owned" badge overlay (top-right corner, if purchased)
    ├── QLabel (name, centered, truncated)
    └── QLabel (price: "Free" / "$4.99", smaller font, #999 or accent color)
```
- **Sizing**: Same formula as PickerCard — `card_size` - 10% for thumb, 22% for label area
- **Hover**: Same states — `rgba(255,255,255,0.08)` bg, `rgba(255,255,255,0.12)` border
- **Selected**: Same blue accent — `rgba(29,101,202,0.25)` bg
- **Tooltip**: Name, creator, price, rating, download count, description preview
- **Click**: Single click selects, double click opens detail or starts download (if owned)
- **"Owned" badge**: Small green checkmark or "Owned" pill at top-right of thumbnail
- **Price label**: "Free" in green (#7db305), "$X.XX" in white/accent

### Existing Widgets to Reuse
- `PickerCard` pattern from `library_ui.py` — clone and extend, don't subclass
- `CustomTooltipWidget` from `custom_button.py` — for rich hover tooltips
- `CustomButton` from `custom_button.py` — for action buttons
- `TextSegmentControl` from `custom_segment_control.py` — already handles My Library / BGEN Library switching
- Grid layout pattern from `LibraryPageController.refresh()` — dynamic columns based on viewport width

### Existing BGEN Library Widgets (already scaffolded in blender_ui.py ~lines 839-890)
- `self.bgen_library_grid` — QGridLayout, margins 8/spacing 10, top-left aligned
- `self.bgen_library_grid_container` — QWidget container
- `self.bgen_library_grid_area` — QScrollArea with styled scrollbar
- `self.bgen_category_dropdown` — QComboBox with "Picker" item
- These get wired to `MarketplaceGridController` (catalogue view)

### Widget Hierarchy for BGEN Library page
```
bgen_library_widget (QWidget)
└── QVBoxLayout
    ├── Toolbar Row (QHBoxLayout)
    │   ├── Explore icon button (switches to Explore view)
    │   ├── Catalogue icon button (switches to Catalogue view)
    │   ├── Category dropdown (existing self.bgen_category_dropdown)
    │   ├── Filter icon button
    │   └── Search icon button (toggles search bar)
    └── QStackedWidget (Explore / Catalogue views)
        ├── Index 0: ExplorePageWidget (curated storefront)
        │   └── QScrollArea with featured content, hero cards, sections
        └── Index 1: Catalogue grid
            └── QScrollArea (existing self.bgen_library_grid_area)
                └── Grid of MarketplaceCards
```

---

## New Files to Create

| File | Purpose |
|---|---|
| `src/marketplace_manager.py` | Singleton: catalog loading, purchase flow, download, entitlement cache |
| `src/marketplace_ui.py` | MarketplaceCard, ExplorePageWidget, MarketplaceGridController, PurchaseOverlay, ProductDetailPanel |

## Existing Files to Modify

| File | Changes |
|---|---|
| `src/auth_manager.py` | Add `sign_in_with_google()` method (browser OAuth + token capture) |
| `src/settings_page.py` | Add "Sign in with Google" button to AccountSection signed-out state |
| `src/supabase_client.py` | Add `download_file()` for streaming binary downloads, add Google OAuth URL builder |
| `src/config/settings.py` | Add Google OAuth client ID, marketplace cache TTL, polling constants |
| `src/blender_ui.py` | Replace BGEN Library placeholder (lines ~839-884) with MarketplaceGridController; wire Google OAuth signals |
| `src/library_manager.py` | Add `install_from_marketplace()` method |

---

## Implementation Phases (UI-First Approach)

### Phase 1A: Auth Improvements
Fix session management issues + add Google OAuth.

1. **Fix account switching**: Add auto sign-out in `_on_session_received()` before processing new session (auth_manager.py line 234)
2. **Add `sign_out_all_devices()`**: New method in AuthManager + add `scope` param to `supabase_client.py` `sign_out()`
3. **Add "Sign out all devices" UI**: Button in AccountSection signed-in state (settings_page.py)
4. Enable Google provider in Supabase Dashboard (Auth > Providers)
5. Create Google Cloud OAuth credentials (client ID + secret)
6. Add `sign_in_with_google()` to `auth_manager.py` (browser redirect + token capture)
7. Add "Sign in with Google" button to `settings_page.py` AccountSection (signed-out state)
8. Test: account switch cleans up old session → Google sign-in works → sign out all devices invalidates everywhere

### Phase 1B: Client-Side Marketplace UI & Mock Data
Build the full marketplace experience with mock data so UX can be iterated before committing to backend structure.

6. Create `marketplace_manager.py` — singleton with mock catalog data, mock entitlements, simulated purchase/download flows
7. Create `marketplace_ui.py`:
   - `MarketplaceCard` — extends PickerCard pattern with price label + "Owned" badge
   - `MarketplaceGridController` — manages Catalogue grid (same pattern as LibraryPageController)
   - `ExplorePageWidget` — curated storefront with featured items, hero cards, category sections
   - `PurchaseOverlay` — modal for purchase flow states
   - `ProductDetailPanel` — expanded product view
8. Restructure BGEN Library tab in `blender_ui.py` (~lines 839-884):
   - Add Explore/Catalogue toggle icons to toolbar
   - Add QStackedWidget for Explore vs Catalogue sub-views
   - Wire existing `bgen_library_grid` as Catalogue view
   - Create ExplorePageWidget as Explore view
9. Add `download_file()` streaming method to `supabase_client.py`
10. Add marketplace constants to `config/settings.py` (cache TTL, polling intervals)
11. Add `install_from_marketplace()` to `library_manager.py`
12. Test full UI flow with mock data: Explore page renders → switch to Catalogue → browse cards → simulated buy → simulated download → install to library

### Phase 1C: Backend Infrastructure
Once UI is solid, wire up the real backend.

13. Create Supabase tables (`marketplace_products`, `marketplace_purchases`, `user_profiles`) + RLS policies
14. Create `teams`, `team_members`, `team_library` tables (schema only — not wired yet, but ready)
15. Create products on Polar dashboard + attach File Download benefits with .bpicker files
16. Set up Polar webhook endpoint pointing to `polar-webhook` Edge Function
17. Deploy Edge Functions: `create-checkout`, `polar-webhook`, `generate-download-url`
18. Switch `marketplace_manager.py` from mock data to real Supabase queries
19. End-to-end test: browse → buy (Polar sandbox) → webhook → download → install

### Phase 2: Enhanced UX
14. Product detail panel with preview carousel
15. Purchase overlay with animated waiting state
16. "Owned" badges via bulk entitlement check
17. Download progress bar in cards
18. Re-download previously purchased items

### Phase 3: Reviews & Ratings
19. Create `marketplace_reviews` table + RLS
20. Review UI in product detail panel
21. Rating aggregation via Postgres trigger

### Phase 4: Creator System (future)
22. Creator profiles + application/approval flow
23. Upload flow for sellers
24. Revenue sharing via Polar
25. Admin moderation

### Phase 5: Studio/Team System (future)
26. Team creation + invite flow UI
27. Wire `teams`, `team_members` tables + RLS
28. Team library: shared cloud .bpicker upload/download
29. Team purchases: buy once → all members access
30. Email domain auto-join (e.g., `@studio.com` → auto-join team)
31. Team billing via Polar subscription
32. Storage quota management

---

## Verification Plan

1. **Auth flow (OTP)**: Sign in via OTP → verify token available for marketplace API calls
2. **Auth flow (Google)**: Sign in via Google OAuth → verify same token/session system works
3. **Auth method switching**: Sign out → sign in with different method → verify same user profile
2. **Catalog browsing**: Load published products, verify cards render with thumbnails
3. **Free download (signed in)**: Download a free item → verify purchase record created (price=0) → file installs
4. **Free download (not signed in)**: Verify redirect to Account sign-in page
5. **First purchase (browser)**: Click Buy → complete on Polar sandbox → webhook fires → addon polls and detects → download succeeds
6. **Entitlement gating**: Verify unauthenticated/unpurchased users cannot generate download URLs
7. **Webhook security**: Send unsigned webhook → verify rejection; send valid webhook → verify purchase recorded
11. **Token expiry**: Let token expire → verify auto-refresh → verify marketplace still works
