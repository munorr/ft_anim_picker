-- =============================================================
-- Decouple creator_profiles from auth.users
--
-- Before: id UUID PRIMARY KEY REFERENCES auth.users(id)
-- After:  creator_id UUID PRIMARY KEY DEFAULT gen_random_uuid()
--         user_id UUID UNIQUE REFERENCES auth.users(id)  (nullable)
--
-- Also renames id → creator_id on creator_profiles, and updates
-- all FKs, triggers, indexes, and RLS policies accordingly.
-- =============================================================

-- -----------------------------------------------------------
-- 1. Add user_id column (initially nullable for migration)
-- -----------------------------------------------------------
ALTER TABLE creator_profiles
    ADD COLUMN IF NOT EXISTS user_id UUID;

-- Backfill: existing rows have id == auth user id
UPDATE creator_profiles SET user_id = id WHERE user_id IS NULL;

-- UNIQUE + FK (nullable — unclaimed profiles have user_id = NULL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'creator_profiles_user_id_key'
    ) THEN
        ALTER TABLE creator_profiles ADD CONSTRAINT creator_profiles_user_id_key UNIQUE (user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'creator_profiles_user_id_fkey'
    ) THEN
        ALTER TABLE creator_profiles
            ADD CONSTRAINT creator_profiles_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;
    END IF;
END $$;

-- -----------------------------------------------------------
-- 2. Drop ALL foreign keys that reference creator_profiles(id)
--    before we rename the column
-- -----------------------------------------------------------

-- Drop FK from id -> auth.users(id)
DO $$
DECLARE
    _conname TEXT;
BEGIN
    SELECT tc.constraint_name INTO _conname
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_name = 'creator_profiles'
      AND tc.constraint_type = 'FOREIGN KEY'
      AND kcu.column_name = 'id'
    LIMIT 1;

    IF _conname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE creator_profiles DROP CONSTRAINT %I', _conname);
    END IF;
END $$;

-- Drop FKs on other tables that reference creator_profiles(id)
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT tc.table_name, tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.referential_constraints rc
            ON tc.constraint_name = rc.constraint_name
        JOIN information_schema.key_column_usage kcu
            ON rc.unique_constraint_name = kcu.constraint_name
        WHERE kcu.table_name = 'creator_profiles'
          AND kcu.column_name = 'id'
          AND tc.constraint_type = 'FOREIGN KEY'
    LOOP
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', r.table_name, r.constraint_name);
    END LOOP;
END $$;

-- -----------------------------------------------------------
-- 3. Rename id → creator_id
-- -----------------------------------------------------------
ALTER TABLE creator_profiles RENAME COLUMN id TO creator_id;

-- Set default for new rows
ALTER TABLE creator_profiles
    ALTER COLUMN creator_id SET DEFAULT gen_random_uuid();

-- -----------------------------------------------------------
-- 4. Re-create FKs on dependent tables pointing to creator_id
-- -----------------------------------------------------------

-- creator_followers.creator_id → creator_profiles.creator_id
ALTER TABLE creator_followers
    ADD CONSTRAINT creator_followers_creator_id_fkey
    FOREIGN KEY (creator_id) REFERENCES creator_profiles(creator_id) ON DELETE CASCADE;

-- marketplace_transactions.creator_id → creator_profiles.creator_id
ALTER TABLE marketplace_transactions
    ADD CONSTRAINT marketplace_transactions_creator_id_fkey
    FOREIGN KEY (creator_id) REFERENCES creator_profiles(creator_id);

-- creator_earnings.creator_id → creator_profiles.creator_id
ALTER TABLE creator_earnings
    ADD CONSTRAINT creator_earnings_creator_id_fkey
    FOREIGN KEY (creator_id) REFERENCES creator_profiles(creator_id);

-- creator_payouts.creator_id → creator_profiles.creator_id
ALTER TABLE creator_payouts
    ADD CONSTRAINT creator_payouts_creator_id_fkey
    FOREIGN KEY (creator_id) REFERENCES creator_profiles(creator_id);

-- marketplace_sections.creator_id → creator_profiles.creator_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'marketplace_sections' AND column_name = 'creator_id'
    ) THEN
        ALTER TABLE marketplace_sections
            ADD CONSTRAINT marketplace_sections_creator_id_fkey
            FOREIGN KEY (creator_id) REFERENCES creator_profiles(creator_id);
    END IF;
END $$;

-- marketplace_products.creator_id → creator_profiles.creator_id
DO $$
DECLARE
    _conname TEXT;
BEGIN
    -- Drop existing FK on marketplace_products.creator_id (may point to auth.users)
    SELECT tc.constraint_name INTO _conname
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_name = 'marketplace_products'
      AND tc.constraint_type = 'FOREIGN KEY'
      AND kcu.column_name = 'creator_id'
    LIMIT 1;

    IF _conname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE marketplace_products DROP CONSTRAINT %I', _conname);
    END IF;
END $$;

ALTER TABLE marketplace_products
    ADD CONSTRAINT marketplace_products_creator_id_fkey
    FOREIGN KEY (creator_id) REFERENCES creator_profiles(creator_id);

-- -----------------------------------------------------------
-- 5. Update RLS policies
-- -----------------------------------------------------------

-- creator_profiles: update own profile
DROP POLICY IF EXISTS "Creators can update own profile" ON creator_profiles;
CREATE POLICY "Creators can update own profile"
    ON creator_profiles FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- marketplace_transactions: creators read own
DROP POLICY IF EXISTS "Creators can read own transactions" ON marketplace_transactions;
CREATE POLICY "Creators can read own transactions"
    ON marketplace_transactions FOR SELECT
    USING (
        creator_id IN (
            SELECT creator_id FROM creator_profiles WHERE user_id = auth.uid()
        )
    );

-- creator_earnings: creators read own
DROP POLICY IF EXISTS "Creators can read own earnings" ON creator_earnings;
CREATE POLICY "Creators can read own earnings"
    ON creator_earnings FOR SELECT
    USING (
        creator_id IN (
            SELECT creator_id FROM creator_profiles WHERE user_id = auth.uid()
        )
    );

-- creator_payouts: creators read own
DROP POLICY IF EXISTS "Creators can read own payouts" ON creator_payouts;
CREATE POLICY "Creators can read own payouts"
    ON creator_payouts FOR SELECT
    USING (
        creator_id IN (
            SELECT creator_id FROM creator_profiles WHERE user_id = auth.uid()
        )
    );

-- -----------------------------------------------------------
-- 6. Update triggers to use creator_id column name
-- -----------------------------------------------------------

-- 6a. Sales stats trigger
CREATE OR REPLACE FUNCTION update_creator_sales_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.status = 'completed' THEN
        UPDATE creator_profiles SET
            total_sales_count = total_sales_count + 1,
            total_revenue_cents = total_revenue_cents + NEW.creator_net_cents,
            updated_at = now()
        WHERE creator_id = NEW.creator_id;
    ELSIF TG_OP = 'UPDATE' AND OLD.status = 'completed' AND NEW.status = 'refunded' THEN
        UPDATE creator_profiles SET
            total_sales_count = GREATEST(total_sales_count - 1, 0),
            total_revenue_cents = total_revenue_cents - OLD.creator_net_cents,
            updated_at = now()
        WHERE creator_id = NEW.creator_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 6b. Product count trigger
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
        WHERE creator_id = target_creator_id;
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 6c. Follower count trigger
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
    WHERE creator_id = target_creator_id;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- -----------------------------------------------------------
-- 7. Index on user_id for fast lookups
-- -----------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_creator_profiles_user_id
    ON creator_profiles(user_id);
