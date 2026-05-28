# BGEN Library: External UI Hosting Options

## Context

The BGEN Library UI is currently built as native Qt widgets (~4,350 lines of `library_ui.py` duplicated across Blender and Maya). Every UI change requires pushing an addon update to both platforms. The goal is to:
1. **Decouple the library UI** so it can be updated independently of the addon
2. **Reuse the same UI** across Blender addon, Maya addon, and eventually a standalone website
3. **Keep native integration** for downloads, library imports, and auth

---

## 5 Approaches Compared

### Approach 1: Embedded WebView (QWebEngineView) ⭐ Recommended

Replace the Qt widget library UI with a hosted web app (React/Vue/Svelte) loaded inside QWebEngineView. Communicate with the addon via QWebChannel bridge.

**How it works:**
- Web app hosted on Vercel/Netlify, loaded by URL inside the addon
- A `LibraryBridge` (QObject) exposes ~10 slots for JS→Python calls (download, auth token, addon info)
- Python pushes events to JS via `page.runJavaScript()` (download progress, auth changes)
- Same web app runs standalone on a website (detects bridge absence, uses native web APIs instead)

**This pattern already exists in your codebase** — `stripe_checkout_dialog.py` uses QWebEngineView + QWebChannel + `_StripeBridge` for Stripe Payment Element. This approach scales that proven pattern.

| Factor | Rating |
|--------|--------|
| Update independence | Excellent — deploy web app anytime, no addon update needed |
| Cross-platform reuse | Excellent — one web app for Blender, Maya, AND website |
| Dev effort | Medium-High — 3-5 weeks for web app + bridge |
| UX quality | Good — web rendering is smooth; slight first-load delay |
| Code reduction | ~8,700 lines of library_ui.py eliminated, replaced by ~200-line wrapper + bridge |
| Offline support | Moderate — Service Worker caching for shell + catalog |
| Memory overhead | ~80-120MB for Chromium process (already loaded for Stripe checkout) |

**Real-world examples:** Discord (React in embedded Chromium), Steam (web store in desktop client), VS Code extensions library, Unity Asset Store (moved from native to web), Figma plugin library.

---

### Approach 2: Remote QML/Qt Quick

Load QML files from a remote server instead of Qt widgets.

| Factor | Rating |
|--------|--------|
| Update independence | Moderate — new QML types still need addon updates |
| Cross-platform reuse | Poor — QML doesn't run in browsers, so website needs separate code |
| Dev effort | High — complete rewrite in QML, mixing QML + QWidgets is complex |
| Offline support | Poor — no Service Worker equivalent |

**Verdict: Not recommended.** Solves the update problem but creates new ones. QML is a dead end for website reuse. Maya's PySide2 has limited QML support.

---

### Approach 3: Server-Driven UI (SDUI)

Server sends JSON layout definitions; the addon has a generic Qt renderer that maps JSON nodes to widgets.

| Factor | Rating |
|--------|--------|
| Update independence | Good — new layouts are server-driven, but new widget types need addon updates |
| Cross-platform reuse | Poor — Qt renderer is useless for a website; need a separate web renderer |
| Dev effort | Medium — JSON schema + renderer (~1500 lines), still duplicated per platform |
| UX quality | Excellent — fully native Qt widgets |

**Verdict: Partial value.** Your explore page layout (`fetch-explore-layout` returning sections) is already SDUI-like. Useful as a content layer inside any approach, but doesn't solve the core problem of dual-platform code or website reuse.

---

### Approach 4: Hybrid — WebView for Browse, Native for Actions

Use QWebEngineView for browsing/discovery only. Keep native Qt for downloads, auth dialogs, library management.

| Factor | Rating |
|--------|--------|
| Update independence | Good — browse UI (most frequent changes) is server-side |
| Cross-platform reuse | Good — browse experience shared; auth/download still duplicated |
| Dev effort | Medium — smaller web app scope |
| UX quality | Good — native feel for actions, web for content |

**Verdict: Good pragmatic middle ground.** Gets 80% of the benefit with 60% of the effort. Could be a stepping stone toward full Approach 1.

---

### Approach 5: Standalone Website + Deep Links (bgen://...)

Build a full web library. Desktop actions triggered via custom URL protocol handlers.

| Factor | Rating |
|--------|--------|
| Update independence | Excellent — website is fully independent |
| Cross-platform reuse | Excellent for web, poor for in-addon experience |
| Dev effort | Medium — web app + protocol handler registration |
| UX quality | Poor — context-switching between browser and addon is jarring |

**Verdict: Not recommended as primary approach.** Users browsing inside Blender/Maya should not be ejected to a browser. Good as a supplementary channel alongside an embedded approach.

---

## Summary Comparison

| | WebView | Remote QML | SDUI | Hybrid | Website+Links |
|--|---------|-----------|------|--------|--------------|
| Update independence | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Website reuse | ⭐⭐⭐ | ❌ | ❌ | ⭐⭐ | ⭐⭐⭐ |
| Dev effort | Medium | High | Medium | Low-Med | Medium |
| Native UX feel | Good | Good | Excellent | Good | Poor |
| Code reduction | ~8,700 lines | 0 | 0 | ~5,000 | ~8,700 |
| Proven in codebase | Yes (Stripe) | No | Partial | Yes | No |

---

## Recommended Path: Approach 1 (Embedded WebView)

### Why
1. **Already proven** — `stripe_checkout_dialog.py` demonstrates QWebEngineView + QWebChannel works in your stack
2. **Maximum reuse** — one web app powers Blender, Maya, and website
3. **Largest code reduction** — eliminates ~8,700 lines of duplicated Qt library UI
4. **True update independence** — deploy the web app via CI/CD; addon only updates if the bridge API changes
5. **Industry standard** — Discord, Steam, VS Code, Unity, Figma all use this pattern

### Bridge API (the stable contract between addon and web app)

```
JS → Python (QWebChannel slots):
  getAuthToken()          → returns access_token string
  downloadProduct(id)     → triggers native download pipeline
  getAddonInfo()          → returns {version, platform, features}
  openLibrary()           → switches addon to library tab
  signIn() / signOut()    → delegates to native AuthManager

Python → JS (via runJavaScript):
  onDownloadProgress(id, done, total)
  onDownloadComplete(id, path)
  onAuthStateChanged(isSignedIn)
  onTokenRefreshed(newToken)
```

### Implementation Phases

**Phase 1: Bridge Layer (1-2 days)**
- Create `LibraryBridge(QObject)` modeled after `_StripeBridge`
- Create `LibraryWebView(QWidget)` wrapping QWebEngineView
- Wire LibraryManager signals to push JS updates

**Phase 2: Web App MVP (3-4 weeks)**
- React + TypeScript + Tailwind (or similar)
- Supabase JS client for data fetching
- Bridge detection: `window.qt?.webChannelTransport` → in-addon vs website mode
- Pages: Explore, Product Grid, Product Detail, Creator Profile, Owned Items
- Dark theme matching current addon aesthetic

**Phase 3: Addon Integration (3-5 days)**
- Replace Qt library widgets with `LibraryWebView` in both Blender and Maya
- LibraryManager stays intact (handles downloads, caching, token refresh)
- AuthManager stays intact (tokens shared via bridge)

**Phase 4: Website Deployment (1 week)**
- Same React app with conditional logic for web-native auth and downloads
- Deploy to custom domain

**Phase 5: Cleanup**
- Delete `library_ui.py` from both platforms (~8,700 lines removed)
- Optionally migrate Stripe checkout into web app (removing `stripe_checkout_dialog.py`)

### Key Files
- `blender/ft_anim_picker/src/stripe_checkout_dialog.py` — reference pattern to replicate
- `blender/ft_anim_picker/src/library_ui.py` — defines all UI to replicate in web app
- `blender/ft_anim_picker/src/library_manager.py` — signal interface defines bridge contract
- `blender/ft_anim_picker/src/auth_manager.py` — `get_token_snapshot()` is key bridge method
- `blender/ft_anim_picker/src/config/settings.py` — needs new `LIBRARY_WEB_URL` setting

---

## Deep Dive: Security

### Auth Token Exposure

**Current baseline (for context):** Tokens are already stored as **plaintext JSON** in `auth_prefs.json` on disk, passed as raw strings to worker threads, and embedded directly in Stripe checkout HTML via f-strings. Error logging (`traceback.print_exc()`) can leak tokens to console. So the current system is not especially hardened.

**With WebView approach — two token architecture options:**

**Option A: Addon holds tokens, bridge shares on-demand (simpler)**
- AuthManager continues to own the session (OTP, OAuth, refresh cycle)
- Web app calls `bridge.getAuthToken()` when it needs to make an API call
- Token lives in JS memory briefly, never persisted in browser storage
- **Risk:** Token is accessible via JS `console` or DevTools in the WebView
- **Mitigation:** Disable DevTools in production (`QWebEnginePage.settings().setAttribute(WebAttribute.JavascriptCanAccessClipboard, False)` + `QTWEBENGINE_CHROMIUM_FLAGS=--disable-dev-tools`). The token is no more exposed than it currently is in `auth_prefs.json` on disk.

**Option B: Addon acts as API proxy — web app never sees tokens (more secure)**
- Web app never gets the raw token at all
- Instead of calling Supabase directly, the web app calls bridge methods: `bridge.fetchProducts()`, `bridge.fetchExploreLayout()`, etc.
- Python-side LibraryManager makes the API calls with the token and returns data to JS
- **Advantage:** Token never enters the web context. Zero exposure risk.
- **Tradeoff:** More bridge methods (~15-20 instead of ~10). Slightly more coupling between web app and addon. The web app can't call Supabase directly, so the website version needs its own API layer.
- **This is how Discord does it** — the Electron app proxies API calls through Node.js IPC, the web client calls APIs directly.

**Recommendation:** Start with **Option A** (simpler, matches current security level), then upgrade to **Option B** later if needed. The current system already has the token in plaintext on disk, so Option A is no worse. Option B is the gold standard if you want to harden security later.

### Data Privacy

- **Purchases/payment info:** Never touches the web app. Stripe handles card data via their hosted iframe (Payment Element). Your addon/web app only sees a `payment_intent_id` string — never card numbers.
- **Browsing activity:** The hosted web app loads from your domain (e.g., `library.bgen.app`). You control the server, so no third-party tracking unless you add it. No cookies are shared with other sites.
- **Product catalog:** Already public data (fetched via anon key). No privacy concern.
- **User ratings/purchases history:** Protected by Supabase RLS — each user can only see their own data, enforced server-side regardless of what the client does.
- **QWebEngineView isolation:** Use an off-the-record profile (as the Stripe checkout already does) — no persistent cookies, localStorage, or cache survive across sessions. Or use a named profile with controlled storage if you want Service Worker caching.

---

## Deep Dive: Performance & Speed

### Ongoing Responsiveness (scrolling, filtering, navigation)

**How it compares to current Qt widgets:**

| Operation | Current Qt | WebView (React) | Notes |
|-----------|-----------|-----------------|-------|
| Scroll product grid | Native QScrollArea, smooth | Browser compositor, smooth | Both hardware-accelerated. Web may actually be smoother due to CSS `will-change` and GPU compositing |
| Filter/search | Python re-renders grid (~150ms debounce) | JS filters in-memory, re-renders virtual list (~16ms) | Web is faster — React virtual lists only render visible items |
| Page navigation | QStackedWidget instant swap | Client-side routing, <50ms | Comparable |
| Image loading | Python QThread + QPixmap | Browser native `<img>` lazy loading | Browser is optimized for this; connection pooling, parallel fetches |
| Hover/animations | Custom `paintEvent` + QPainter | CSS transitions (GPU-accelerated) | Web animations are typically smoother |

**Key technique:** Use a **virtual/windowed list** (e.g., `react-window` or `@tanstack/virtual`) for the product grid. This only renders the ~20-30 visible cards, not all 200+. The current Qt implementation creates all `LibraryCard` widgets upfront, which is actually *less* efficient than a virtualized web list.

**Bottom line:** For a library UI (scrolling grids, images, text), web rendering is on par with or better than Qt widgets. The gap would only show for complex real-time graphics (not applicable here).

### Memory / Resource Usage

**The Chromium question:**

- QWebEngineView spawns a Chromium renderer process. Typical base overhead: **60-100MB**.
- However, your addon **already loads QWebEngineView** for Stripe checkout (`stripe_checkout_dialog.py`). The Chromium process is already being spawned.
- If you keep the library WebView as a **persistent singleton** (created once, hidden when not on the library tab), there's **no additional process spawn** — just the JS heap of your web app (~10-30MB for a React app with product data).

**Mitigation strategies:**
1. **Lazy init:** Don't create the WebView until the user first opens the library tab. Most picker users may never open it.
2. **Shared process:** Qt allows sharing a single `QWebEngineProfile` across multiple pages. The Stripe checkout and library can share one Chromium process.
3. **Page lifecycle:** When the user navigates away from the library, call `page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)` — this tells Chromium to suspend JS timers and reduce memory. Resume when they come back.
4. **Aggressive cleanup:** If memory is critical, destroy the WebView when leaving the tab and recreate on return. First load is ~1-2s, but reclaims all memory.

**Realistic impact:** For users who open the library, expect ~80-100MB total for the WebView (shared with Stripe checkout). For users who never open it, 0MB overhead (lazy init). Blender typically uses 2-8GB, so this is 1-5% at most.

### Offline / Slow Network

**Current behavior (Qt widgets):**
- `library_cache.json` stores products, sections, feature flags on disk
- On startup, loads from cache if server unreachable
- TTLs: products 5min, entitlements 10min, flags 1hr
- Shows "Store Offline" banner if no cache AND no network

**WebView approach can match or exceed this:**

| Scenario | Strategy |
|----------|----------|
| **First ever load, no network** | Web app can't load at all. Show a native Qt fallback message: "Library requires internet for first use." This is the one scenario that's worse than current. |
| **Returning user, no network** | **Service Worker** caches the entire web app shell (HTML/JS/CSS). App loads instantly from cache. Product data cached in IndexedDB (mirrors current `library_cache.json`). Thumbnails cached by Service Worker. User sees cached catalog with "Offline" banner. |
| **Slow network (high latency)** | Service Worker serves cached shell immediately (app appears in <100ms). Data fetches happen in background. Show stale data with "Updating..." indicator, swap in fresh data when ready. This is actually better UX than current Qt approach which shows a loading spinner. |
| **Intermittent connection** | Service Worker + background sync. Queue failed requests, retry when connection returns. |

**The key insight:** Service Workers give you the same caching your `library_cache.json` provides, but with more granular control and browser-native optimization. The **only regression** is the first-ever cold start requiring network — which is also true of the current approach (you can't browse products you've never fetched).

**To eliminate even that regression:** Bundle a minimal "app shell" HTML file with the addon (~50KB). Load it from disk on first use, then the Service Worker takes over for future loads. This gives you instant first load + automatic updates.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| First-load latency | Service Worker caching; optionally bundle app shell HTML with addon for instant first load |
| QWebEngineView memory | Lazy init (0MB if library never opened); share Chromium process with Stripe checkout; freeze page when hidden |
| PySide2 (Maya) gaps | PySide2 supports QWebEngineView; test early on Maya 2022-2025 |
| Bridge versioning | `bridge.getVersion()` lets web app adapt to older addon versions |
| Offline users | Service Worker caches shell + catalog in IndexedDB; stale-while-revalidate pattern |
| Token exposure in WebView | Option A: brief JS memory only, DevTools disabled. Option B (more secure): addon proxies all API calls, token never enters web context |
| Data privacy | Off-the-record QWebEngineProfile; Stripe handles all card data; RLS enforces server-side access control |

---

## Deep Dive: Web Framework & Hosting Choice

### Framework Comparison

| | React | Vue | Svelte |
|--|-------|-----|--------|
| **Bundle size** | ~45KB gzipped (React + ReactDOM) | ~33KB gzipped | ~2KB (compiler, no runtime) |
| **Ecosystem** | Largest — Supabase JS, Stripe Elements, TanStack Virtual all have first-class React support | Good — Supabase & Stripe have Vue wrappers | Growing — Supabase works, Stripe needs manual integration |
| **Supabase integration** | `@supabase/auth-ui-react` official component library; `@supabase/supabase-js` works natively | Community wrapper `@supabase/auth-ui-vue` | No official auth UI; `supabase-js` works but auth UI must be custom |
| **Stripe integration** | `@stripe/react-stripe-js` official; drop-in Payment Element | `@stripe/stripe-js` + manual mount | `@stripe/stripe-js` + manual mount |
| **Learning curve** | You're likely most familiar with it (most popular); JSX is intuitive | Similar to React; template syntax | Different mental model (reactivity); smallest community for help |
| **SSR/SSG for website** | Next.js (Vercel's framework) — excellent for SEO, fast loads | Nuxt.js — good equivalent | SvelteKit — excellent but smaller ecosystem |
| **Developer hiring** | Easiest to find React developers if you ever need help | Moderate | Harder |
| **Performance** | Good with virtual DOM; fine for this use case | Similar to React | Best raw performance (no virtual DOM) — but overkill for a library |

**Recommendation: React + Next.js**

Why:
1. **Supabase has official React components** — auth UI, real-time subscriptions, storage helpers. You won't build these from scratch.
2. **Stripe has official React bindings** — `<PaymentElement>` component drops right in, replacing your current hand-built HTML checkout.
3. **Next.js gives you both modes free** — embedded in addon (client-side SPA mode) AND SEO-friendly website (SSR mode) from the same codebase.
4. **TanStack Virtual** (React) for virtualized product grids — proven at scale.
5. **Tailwind CSS** for styling — utility-first, easy to match your dark theme tokens (`#1d1d1d`, `#e0e0e0`, `#1D65CA`).

If you strongly prefer a smaller bundle and don't need the React ecosystem, **Svelte + SvelteKit** is the runner-up. But you'd be writing more integration code yourself.

### Hosting Comparison

| | Vercel | Netlify | Supabase Hosting | Self-hosted (VPS) |
|--|--------|---------|------------------|-------------------|
| **Cost** | Free tier generous (100GB bandwidth); Pro $20/mo | Free tier similar; Pro $19/mo | Not yet GA for frontend | $5-20/mo (DigitalOcean/Hetzner) |
| **Deploy speed** | Push to git → live in ~30s | Push to git → live in ~45s | N/A | Manual or CI/CD setup needed |
| **CDN** | Global edge network (Vercel Edge) | Global CDN (Cloudflare-backed) | N/A | Must configure Cloudflare separately |
| **Next.js support** | **Best** — Vercel built Next.js; zero-config | Good but some Next.js features limited | N/A | Full control but manual setup |
| **Preview deploys** | Yes — every PR gets a preview URL | Yes — same | N/A | Must set up yourself |
| **Custom domain** | Yes, free SSL | Yes, free SSL | N/A | Yes, with Let's Encrypt |
| **Supabase proximity** | Can deploy to same region as your Supabase project | Same | Already co-located | Depends on VPS location |

**Recommendation: Vercel**

Why:
1. **Built for Next.js** — zero-config deployment, optimal performance.
2. **Preview deploys** — every PR gets a URL you can test in your QWebEngineView before merging. Invaluable for library UI changes.
3. **Edge caching** — static assets (JS/CSS/images) served from the nearest edge node globally. Minimizes first-load time in the WebView.
4. **Free tier** is sufficient for your scale. Pro ($20/mo) when you outgrow it.
5. **Environment variables** — easy to configure `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_STRIPE_KEY` per environment (staging/production).

### Recommended Tech Stack Summary

```
Framework:    React 18+ with Next.js 14+ (App Router)
Language:     TypeScript
Styling:      Tailwind CSS (matches your dark theme tokens)
State:        Zustand or React Context (lightweight, no Redux overhead)
Data:         @supabase/supabase-js + TanStack Query (caching, revalidation)
Payments:     @stripe/react-stripe-js (official Payment Element)
Virtualization: @tanstack/react-virtual (product grid)
Hosting:      Vercel (free tier → Pro)
Domain:       library.bgen.app or store.bgen.app
```

---

## Deep Dive: Migration Strategy

The migration should be **incremental and reversible** at every step. You should never be in a state where the library is broken for users.

### Phase 0: Preparation (1-2 days)
**Goal:** Set up the web project and confirm QWebEngineView works reliably.

1. Create a new repo (or monorepo folder): `bgen-library-web/`
2. `npx create-next-app@latest` with TypeScript + Tailwind
3. Create a minimal "Hello from BGEN Library" page
4. Deploy to Vercel, get a URL (e.g., `https://bgen-library.vercel.app`)
5. In the addon, create a **proof-of-concept** `LibraryWebView` widget:
   - QWebEngineView that loads the Vercel URL
   - QWebChannel with a minimal bridge (just `getAddonInfo()`)
   - Add a hidden toggle in settings or dev flag: `USE_WEBVIEW_LIBRARY = False`
   - When enabled, swap the library page from Qt widgets to the WebView
6. Test in Blender AND Maya — confirm the WebView loads, bridge communicates, no crashes

**Exit criteria:** WebView loads your hosted page in both Blender and Maya. Bridge sends addon info to JS. No crashes. No user-facing changes (flag is off).

### Phase 1: Explore Page in WebView (1-2 weeks)
**Goal:** Replace the Explore page (hero carousel + sections) with the web version while keeping the Qt grid as fallback.

1. Build the Explore page in React:
   - Fetch `fetch-explore-layout` from Supabase (using anon key — no auth needed)
   - Hero carousel, section rows, collection banners
   - Match current dark theme exactly (screenshot the Qt version, pixel-match)
   - Bridge: `getAuthToken()`, `getAddonInfo()`, `navigateToProduct(id)`, `navigateToCollection(id)`
2. In the addon, wire navigation:
   - When JS calls `bridge.navigateToProduct(id)` → addon switches to its existing Qt `ProductDetailPage`
   - When JS calls `bridge.navigateToCollection(id)` → addon switches to its existing Qt `FilteredGridPage`
3. **Feature flag:** `LIBRARY_WEBVIEW_EXPLORE = True/False` — server-side toggle via `library_feature_flags`
   - Roll out to 10% of users first, monitor for issues
   - If problems, flip flag server-side — instant rollback, no addon update

**Exit criteria:** Explore page renders identically in WebView. Navigation to product/collection pages works (landing on existing Qt pages). Flag can enable/disable without addon update.

**Why start here:** The Explore page is the most visually complex (carousel, sections, banners) but the least interactive (no downloads, no purchases). Low risk, high visual impact. Proves the approach works.

### Phase 2: Product Grid + Detail Pages (1-2 weeks)
**Goal:** Move the product browsing experience to the web app.

1. Build in React:
   - Product grid with search, filter, sort, view modes (small/medium/large/list)
   - Virtual scrolling via `@tanstack/react-virtual`
   - Product detail page (description, images, ratings, creator info)
   - Creator profile page
2. Expand bridge:
   - `downloadProduct(id)` → triggers Python download pipeline
   - `initiateCheckout(id)` → triggers Python purchase flow (or handle Stripe directly in web app)
   - Push `onDownloadProgress(id, pct)` and `onDownloadComplete(id)` from Python to JS
3. **Remove Qt pages one by one:**
   - First: `ExplorePageWidget` → already replaced in Phase 1
   - Then: `LibraryGridController` + `LibraryCard` + `LibraryListItem`
   - Then: `ProductDetailPage`
   - Then: `FilteredGridPage`, `CreatorCataloguePage`, `CreatorProfilePage`
4. Each removal behind a flag — if anything breaks, revert that specific page

**Exit criteria:** Full browse + detail experience in WebView. Downloads triggered from web UI work end-to-end. Qt library UI code is dead (but still present as fallback).

### Phase 3: Checkout + Purchases in WebView (3-5 days)
**Goal:** Move Stripe checkout into the web app (it's already web-based anyway).

1. Replace `stripe_checkout_dialog.py` inline HTML with the React Stripe `<PaymentElement>`
2. Purchase history page in React
3. Saved cards management in React
4. The entire purchase flow now lives in the web app

**Exit criteria:** Users can browse, buy, and download entirely within the WebView. No Qt library UI involved.

### Phase 4: Maya Parity (2-3 days)
**Goal:** Same WebView experience in Maya.

1. Copy the `LibraryWebView` + `LibraryBridge` to Maya (should be near-identical, ~200 lines)
2. Test with PySide2 (Maya 2022-2024) and PySide6 (Maya 2025+)
3. Remove Maya's `library_ui.py` (~4,352 lines)

**Exit criteria:** Maya library works identically to Blender via the same hosted web app.

### Phase 5: Website Launch (1 week)
**Goal:** The same React app runs standalone on a website.

1. Add conditional logic: if `window.qt?.webChannelTransport` exists → use bridge; else → use web-native APIs
2. Web-native replacements:
   - Auth: Supabase Auth UI (email + Google OAuth) instead of bridge `signIn()`
   - Downloads: browser `<a download>` instead of bridge `downloadProduct()`
   - No library import (web users download .bpicker files manually)
3. SEO: Next.js SSR for product pages (Google-indexable)
4. Deploy to custom domain (e.g., `library.bgen.app`)

**Exit criteria:** Users can browse, purchase, and download from the website. Same data, same products, same auth system.

### Phase 6: Cleanup (1-2 days)
**Goal:** Remove dead code.

1. Delete `library_ui.py` from both Blender and Maya (~8,700 lines)
2. Delete `stripe_checkout_dialog.py` from both (if checkout is now in web app)
3. Simplify `LibraryManager` — remove thumbnail loading, grid management signals (now handled by web app)
4. Update `blender_ui.py` and Maya `ui.py` — remove all Qt library widget setup code

**Total estimated timeline:** 5-7 weeks (can be parallelized if you have help with the React app)

### Rollback Strategy at Every Phase

```
Phase 0: Remove the dev flag → zero user impact
Phase 1: Flip server-side feature flag → instant rollback to Qt Explore page
Phase 2: Flip per-page flags → rollback individual pages to Qt
Phase 3: Keep stripe_checkout_dialog.py until web checkout is proven → fallback available
Phase 4: Maya can keep its Qt UI independently of Blender
Phase 5: Website is additive — doesn't affect addon
Phase 6: Only delete code after 2+ weeks of stable WebView usage
```

Every phase is independently deployable and reversible. At no point are you "all in" without a fallback.
