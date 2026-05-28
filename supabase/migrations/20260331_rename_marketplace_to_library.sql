-- =============================================================
-- Rename: marketplace_* → library_*
-- Tables, constraints, indexes, triggers, functions, feature flags
-- Plus backward-compatible VIEWs for old addon versions
-- =============================================================

-- -----------------------------------------------------------
-- 1. Rename Tables
-- -----------------------------------------------------------
ALTER TABLE marketplace_products RENAME TO library_products;
ALTER TABLE marketplace_purchases RENAME TO library_purchases;
ALTER TABLE marketplace_ratings RENAME TO library_ratings;
ALTER TABLE marketplace_transactions RENAME TO library_transactions;
ALTER TABLE marketplace_sections RENAME TO library_sections;

-- Note: marketplace_feature_flags may not exist in all environments
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'marketplace_feature_flags') THEN
        EXECUTE 'ALTER TABLE marketplace_feature_flags RENAME TO library_feature_flags';
    END IF;
END $$;

-- -----------------------------------------------------------
-- 2. Rename Foreign Key Constraints
-- -----------------------------------------------------------
DO $$
BEGIN
    -- marketplace_ratings_product_id_fkey → library_ratings_product_id_fkey
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'marketplace_ratings_product_id_fkey') THEN
        ALTER TABLE library_ratings RENAME CONSTRAINT marketplace_ratings_product_id_fkey TO library_ratings_product_id_fkey;
    END IF;

    -- marketplace_transactions_creator_id_fkey → library_transactions_creator_id_fkey
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'marketplace_transactions_creator_id_fkey') THEN
        ALTER TABLE library_transactions RENAME CONSTRAINT marketplace_transactions_creator_id_fkey TO library_transactions_creator_id_fkey;
    END IF;

    -- marketplace_sections_creator_id_fkey → library_sections_creator_id_fkey
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'marketplace_sections_creator_id_fkey') THEN
        ALTER TABLE library_sections RENAME CONSTRAINT marketplace_sections_creator_id_fkey TO library_sections_creator_id_fkey;
    END IF;

    -- marketplace_products_creator_id_fkey → library_products_creator_id_fkey
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'marketplace_products_creator_id_fkey') THEN
        ALTER TABLE library_products RENAME CONSTRAINT marketplace_products_creator_id_fkey TO library_products_creator_id_fkey;
    END IF;
END $$;

-- -----------------------------------------------------------
-- 3. Rename Indexes
-- -----------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_transactions_creator') THEN
        ALTER INDEX idx_transactions_creator RENAME TO idx_library_transactions_creator;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_transactions_product') THEN
        ALTER INDEX idx_transactions_product RENAME TO idx_library_transactions_product;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_transactions_created') THEN
        ALTER INDEX idx_transactions_created RENAME TO idx_library_transactions_created;
    END IF;
END $$;

-- -----------------------------------------------------------
-- 4. Recreate Triggers on renamed tables
-- -----------------------------------------------------------

-- 4a. Drop old triggers (they still reference old table names internally)
DROP TRIGGER IF EXISTS trg_update_product_rating ON library_ratings;
DROP TRIGGER IF EXISTS trg_creator_sales_stats ON library_transactions;
DROP TRIGGER IF EXISTS trg_creator_product_count ON library_products;

-- 4b. Recreate update_product_rating() to reference library_* tables
CREATE OR REPLACE FUNCTION update_product_rating()
RETURNS TRIGGER AS $$
DECLARE
    target_product_id UUID;
BEGIN
    target_product_id := COALESCE(NEW.product_id, OLD.product_id);
    UPDATE library_products SET
        rating_avg = (
            SELECT COALESCE(AVG(rating)::NUMERIC(3,2), 0)
            FROM library_ratings
            WHERE product_id = target_product_id
        ),
        rating_count = (
            SELECT COUNT(*)
            FROM library_ratings
            WHERE product_id = target_product_id
        )
    WHERE id = target_product_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_update_product_rating
    AFTER INSERT OR UPDATE OR DELETE ON library_ratings
    FOR EACH ROW
    EXECUTE FUNCTION update_product_rating();

-- 4c. Recreate update_creator_sales_stats() to reference library_* tables
CREATE OR REPLACE FUNCTION update_creator_sales_stats()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE creator_profiles SET
        total_sales_count = (
            SELECT COUNT(*)
            FROM library_transactions
            WHERE creator_id = NEW.creator_id AND status = 'completed'
        ),
        total_revenue_cents = (
            SELECT COALESCE(SUM(creator_amount_cents), 0)
            FROM library_transactions
            WHERE creator_id = NEW.creator_id AND status = 'completed'
        )
    WHERE creator_id = NEW.creator_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_creator_sales_stats
    AFTER INSERT OR UPDATE ON library_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_creator_sales_stats();

-- 4d. Recreate update_creator_product_count() to reference library_* tables
CREATE OR REPLACE FUNCTION update_creator_product_count()
RETURNS TRIGGER AS $$
DECLARE
    target_creator_id UUID;
BEGIN
    target_creator_id := COALESCE(NEW.creator_id, OLD.creator_id);
    UPDATE creator_profiles SET
        product_count = (
            SELECT COUNT(*)
            FROM library_products
            WHERE creator_id = target_creator_id AND status = 'published'
        )
    WHERE creator_id = target_creator_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_creator_product_count
    AFTER INSERT OR UPDATE OR DELETE ON library_products
    FOR EACH ROW
    EXECUTE FUNCTION update_creator_product_count();

-- -----------------------------------------------------------
-- 5. Update feature flag keys
-- -----------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'library_feature_flags') THEN
        EXECUTE 'UPDATE library_feature_flags SET key = REPLACE(key, ''marketplace_'', ''library_'') WHERE key LIKE ''marketplace_%''';
    END IF;
END $$;

-- -----------------------------------------------------------
-- 6. Update column comment
-- -----------------------------------------------------------
COMMENT ON COLUMN library_products.storage_path IS
    'Path within the library-assets private Storage bucket, e.g. "{product_id}/file.bpicker"';

-- -----------------------------------------------------------
-- 7. Backward-compatible VIEWs (temporary, for old addon versions)
-- -----------------------------------------------------------
CREATE OR REPLACE VIEW marketplace_products AS SELECT * FROM library_products;
CREATE OR REPLACE VIEW marketplace_purchases AS SELECT * FROM library_purchases;
CREATE OR REPLACE VIEW marketplace_ratings AS SELECT * FROM library_ratings;
CREATE OR REPLACE VIEW marketplace_transactions AS SELECT * FROM library_transactions;
CREATE OR REPLACE VIEW marketplace_sections AS SELECT * FROM library_sections;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'library_feature_flags') THEN
        EXECUTE 'CREATE OR REPLACE VIEW marketplace_feature_flags AS SELECT * FROM library_feature_flags';
    END IF;
END $$;
