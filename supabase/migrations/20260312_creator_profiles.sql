-- =============================================================
-- Creator Profiles & Revenue Tracking Migration
-- 1. creator_profiles table
-- 2. creator_followers table
-- 3. marketplace_transactions table (revenue audit trail)
-- 4. creator_earnings ledger
-- 5. creator_payouts table
-- 6. Alter marketplace_products (view_count)
-- 7. Alter marketplace_sections (creator_id for spotlight)
-- 8. Denormalization triggers
-- 9. Storage bucket for creator assets (avatars, banners)
-- =============================================================

-- -----------------------------------------------------------
-- 1. Creator Profiles
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS creator_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    bio TEXT,
    subtitle TEXT,                               -- e.g. "3d Character artist"
    avatar_url TEXT,
    banner_url TEXT,
    social_links JSONB DEFAULT '{}'::jsonb,      -- {youtube, instagram, twitter, website}
    is_verified BOOLEAN DEFAULT false,           -- blue badge
    is_featured BOOLEAN DEFAULT false,           -- show in Creator Catalogue prominently
    seller_status TEXT DEFAULT 'pending'
        CHECK (seller_status IN ('pending', 'approved', 'suspended')),
    payout_split_percent INTEGER DEFAULT 80
        CHECK (payout_split_percent >= 0 AND payout_split_percent <= 100),
    -- Denormalized counters (updated by triggers)
    total_sales_count INTEGER DEFAULT 0,
    total_revenue_cents BIGINT DEFAULT 0,        -- creator's net lifetime earnings
    product_count INTEGER DEFAULT 0,
    follower_count INTEGER DEFAULT 0,
    rating_avg NUMERIC(3,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_creator_profiles_seller_status
    ON creator_profiles(seller_status);
CREATE INDEX IF NOT EXISTS idx_creator_profiles_featured
    ON creator_profiles(is_featured) WHERE is_featured = true;

ALTER TABLE creator_profiles ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Anyone can read approved creators' AND tablename = 'creator_profiles') THEN
        CREATE POLICY "Anyone can read approved creators" ON creator_profiles FOR SELECT USING (seller_status = 'approved');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Creators can update own profile' AND tablename = 'creator_profiles') THEN
        CREATE POLICY "Creators can update own profile" ON creator_profiles FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);
    END IF;
END $$;

-- -----------------------------------------------------------
-- 2. Creator Followers
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS creator_followers (
    creator_id UUID NOT NULL REFERENCES creator_profiles(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (creator_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_creator_followers_user
    ON creator_followers(user_id);

ALTER TABLE creator_followers ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Anyone can read follows' AND tablename = 'creator_followers') THEN
        CREATE POLICY "Anyone can read follows" ON creator_followers FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can insert own follows' AND tablename = 'creator_followers') THEN
        CREATE POLICY "Users can insert own follows" ON creator_followers FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete own follows' AND tablename = 'creator_followers') THEN
        CREATE POLICY "Users can delete own follows" ON creator_followers FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

-- -----------------------------------------------------------
-- 3. Marketplace Transactions (financial audit trail)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS marketplace_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id UUID REFERENCES marketplace_purchases(id),
    product_id UUID NOT NULL REFERENCES marketplace_products(id),
    creator_id UUID NOT NULL REFERENCES creator_profiles(id),
    buyer_id UUID NOT NULL REFERENCES auth.users(id),
    gross_amount_cents INTEGER NOT NULL DEFAULT 0,
    platform_fee_cents INTEGER NOT NULL DEFAULT 0,
    processing_fee_cents INTEGER NOT NULL DEFAULT 0,  -- Polar 4% + $0.40
    creator_net_cents INTEGER NOT NULL DEFAULT 0,      -- What the creator receives
    polar_order_id TEXT,
    status TEXT DEFAULT 'completed'
        CHECK (status IN ('pending', 'completed', 'refunded')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transactions_creator
    ON marketplace_transactions(creator_id);
CREATE INDEX IF NOT EXISTS idx_transactions_product
    ON marketplace_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created
    ON marketplace_transactions(created_at);

ALTER TABLE marketplace_transactions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Creators can read own transactions' AND tablename = 'marketplace_transactions') THEN
        CREATE POLICY "Creators can read own transactions" ON marketplace_transactions FOR SELECT USING (auth.uid() = creator_id);
    END IF;
END $$;

-- No INSERT/UPDATE from client — only Edge Functions (service_role) write

-- -----------------------------------------------------------
-- 4. Creator Earnings Ledger
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS creator_earnings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creator_profiles(id),
    entry_type TEXT NOT NULL
        CHECK (entry_type IN ('sale', 'refund', 'payout', 'adjustment')),
    amount_cents INTEGER NOT NULL,                 -- positive for sale, negative for payout/refund
    balance_after_cents BIGINT NOT NULL DEFAULT 0, -- running balance
    transaction_id UUID REFERENCES marketplace_transactions(id),
    payout_id UUID,                                -- FK added after creator_payouts table exists
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_earnings_creator
    ON creator_earnings(creator_id);
CREATE INDEX IF NOT EXISTS idx_earnings_created
    ON creator_earnings(created_at);

ALTER TABLE creator_earnings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Creators can read own earnings' AND tablename = 'creator_earnings') THEN
        CREATE POLICY "Creators can read own earnings" ON creator_earnings FOR SELECT USING (auth.uid() = creator_id);
    END IF;
END $$;

-- -----------------------------------------------------------
-- 5. Creator Payouts
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS creator_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creator_profiles(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    payout_method TEXT
        CHECK (payout_method IN ('paypal', 'bank_transfer')),
    payout_details JSONB DEFAULT '{}'::jsonb,     -- {paypal_email} or bank info
    period_start DATE,
    period_end DATE,
    processed_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Add the FK from creator_earnings.payout_id now that table exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'creator_earnings_payout_id_fkey'
    ) THEN
        ALTER TABLE creator_earnings
            ADD CONSTRAINT creator_earnings_payout_id_fkey
            FOREIGN KEY (payout_id) REFERENCES creator_payouts(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_payouts_creator
    ON creator_payouts(creator_id);
CREATE INDEX IF NOT EXISTS idx_payouts_status
    ON creator_payouts(status) WHERE status IN ('pending', 'processing');

ALTER TABLE creator_payouts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Creators can read own payouts' AND tablename = 'creator_payouts') THEN
        CREATE POLICY "Creators can read own payouts" ON creator_payouts FOR SELECT USING (auth.uid() = creator_id);
    END IF;
END $$;

-- -----------------------------------------------------------
-- 6. Alter marketplace_products — add view_count
-- -----------------------------------------------------------
ALTER TABLE marketplace_products
    ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0;

-- -----------------------------------------------------------
-- 7. Alter marketplace_sections — add creator_id for spotlight
-- -----------------------------------------------------------
ALTER TABLE marketplace_sections
    ADD COLUMN IF NOT EXISTS creator_id UUID REFERENCES creator_profiles(id);

COMMENT ON COLUMN marketplace_sections.creator_id IS
    'For creator_spotlight sections: links to the creator profile';

-- -----------------------------------------------------------
-- 8. Denormalization Triggers
-- -----------------------------------------------------------

-- 8a. Update creator sales stats on new transaction
CREATE OR REPLACE FUNCTION update_creator_sales_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.status = 'completed' THEN
        UPDATE creator_profiles SET
            total_sales_count = total_sales_count + 1,
            total_revenue_cents = total_revenue_cents + NEW.creator_net_cents,
            updated_at = now()
        WHERE id = NEW.creator_id;
    ELSIF TG_OP = 'UPDATE' AND OLD.status = 'completed' AND NEW.status = 'refunded' THEN
        UPDATE creator_profiles SET
            total_sales_count = GREATEST(total_sales_count - 1, 0),
            total_revenue_cents = total_revenue_cents - OLD.creator_net_cents,
            updated_at = now()
        WHERE id = NEW.creator_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_creator_sales_stats ON marketplace_transactions;
CREATE TRIGGER trg_creator_sales_stats
    AFTER INSERT OR UPDATE ON marketplace_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_creator_sales_stats();

-- 8b. Update creator product count
CREATE OR REPLACE FUNCTION update_creator_product_count()
RETURNS TRIGGER AS $$
DECLARE
    target_creator_id UUID;
BEGIN
    target_creator_id := COALESCE(NEW.creator_id, OLD.creator_id);
    IF target_creator_id IS NOT NULL THEN
        UPDATE creator_profiles SET
            product_count = (
                SELECT COUNT(*)
                FROM marketplace_products
                WHERE creator_id = target_creator_id
                  AND status = 'published'
            ),
            updated_at = now()
        WHERE id = target_creator_id;
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_creator_product_count ON marketplace_products;
CREATE TRIGGER trg_creator_product_count
    AFTER INSERT OR UPDATE OR DELETE ON marketplace_products
    FOR EACH ROW
    EXECUTE FUNCTION update_creator_product_count();

-- 8c. Update creator follower count
CREATE OR REPLACE FUNCTION update_creator_follower_count()
RETURNS TRIGGER AS $$
DECLARE
    target_creator_id UUID;
BEGIN
    target_creator_id := COALESCE(NEW.creator_id, OLD.creator_id);
    UPDATE creator_profiles SET
        follower_count = (
            SELECT COUNT(*)
            FROM creator_followers
            WHERE creator_id = target_creator_id
        ),
        updated_at = now()
    WHERE id = target_creator_id;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_creator_follower_count ON creator_followers;
CREATE TRIGGER trg_creator_follower_count
    AFTER INSERT OR DELETE ON creator_followers
    FOR EACH ROW
    EXECUTE FUNCTION update_creator_follower_count();

-- -----------------------------------------------------------
-- 9. Storage bucket for creator profile assets
-- -----------------------------------------------------------
-- Run via Supabase Dashboard or CLI:
--   INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
--   VALUES ('creator-assets', 'creator-assets', true, 5242880, '{"image/png","image/jpeg","image/webp"}');
--
-- Public bucket for avatars and banners (max 5MB per file).
