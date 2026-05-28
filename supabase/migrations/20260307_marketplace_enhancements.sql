-- =============================================================
-- Marketplace Enhancements Migration
-- 1. webhook_logs table for webhook diagnostics
-- 2. storage_path column on marketplace_products
-- 3. marketplace_ratings table + aggregation trigger
-- =============================================================

-- -----------------------------------------------------------
-- 1. Webhook Logs (diagnostics)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT,
    payload JSONB,
    status TEXT DEFAULT 'received',
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- No RLS needed — only Edge Functions (service_role) insert into this table.
-- If you want to query from Dashboard, leave RLS disabled.

-- -----------------------------------------------------------
-- 2. Add storage_path to marketplace_products
-- -----------------------------------------------------------
ALTER TABLE marketplace_products
    ADD COLUMN IF NOT EXISTS storage_path TEXT;

COMMENT ON COLUMN marketplace_products.storage_path IS
    'Path within the marketplace-assets private Storage bucket, e.g. "{product_id}/file.bpicker"';

-- -----------------------------------------------------------
-- 3. Marketplace Ratings (star ratings, no text reviews)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS marketplace_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    product_id UUID NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, product_id)
);

-- Add foreign key only if marketplace_products exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'marketplace_ratings_product_id_fkey'
    ) THEN
        ALTER TABLE marketplace_ratings
            ADD CONSTRAINT marketplace_ratings_product_id_fkey
            FOREIGN KEY (product_id) REFERENCES marketplace_products(id);
    END IF;
END $$;

ALTER TABLE marketplace_ratings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Anyone can read ratings' AND tablename = 'marketplace_ratings') THEN
        CREATE POLICY "Anyone can read ratings" ON marketplace_ratings FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can insert own ratings' AND tablename = 'marketplace_ratings') THEN
        CREATE POLICY "Users can insert own ratings" ON marketplace_ratings FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can update own ratings' AND tablename = 'marketplace_ratings') THEN
        CREATE POLICY "Users can update own ratings" ON marketplace_ratings FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete own ratings' AND tablename = 'marketplace_ratings') THEN
        CREATE POLICY "Users can delete own ratings" ON marketplace_ratings FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

-- -----------------------------------------------------------
-- 4. Rating Aggregation Trigger
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION update_product_rating()
RETURNS TRIGGER AS $$
DECLARE
    target_product_id UUID;
BEGIN
    target_product_id := COALESCE(NEW.product_id, OLD.product_id);
    UPDATE marketplace_products SET
        rating_avg = (
            SELECT COALESCE(AVG(rating)::NUMERIC(3,2), 0)
            FROM marketplace_ratings
            WHERE product_id = target_product_id
        ),
        rating_count = (
            SELECT COUNT(*)
            FROM marketplace_ratings
            WHERE product_id = target_product_id
        )
    WHERE id = target_product_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_update_product_rating ON marketplace_ratings;

CREATE TRIGGER trg_update_product_rating
    AFTER INSERT OR UPDATE OR DELETE ON marketplace_ratings
    FOR EACH ROW
    EXECUTE FUNCTION update_product_rating();
