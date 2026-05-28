
-- ============================================================
-- SUPABASE PROJECT CONTEXT DUMP
-- ============================================================

-- 1. TABLES & COLUMNS

| section  | table_name                | column_name            | data_type                | is_nullable | column_default           | is_primary_key |
| -------- | ------------------------- | ---------------------- | ------------------------ | ----------- | ------------------------ | -------------- |
| 1_SCHEMA | marketplace_feature_flags | key                    | text                     | NO          | null                     | YES            |
| 1_SCHEMA | marketplace_feature_flags | value                  | jsonb                    | NO          | 'true'::jsonb            | NO             |
| 1_SCHEMA | marketplace_feature_flags | description            | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_feature_flags | updated_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | marketplace_products      | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | marketplace_products      | slug                   | text                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_products      | name                   | text                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_products      | description            | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_products      | short_description      | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_products      | creator_id             | uuid                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_products      | creator                | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_products      | category               | text                     | YES         | '''picker''::text'::text | NO             |
| 1_SCHEMA | marketplace_products      | tags                   | ARRAY                    | YES         | '{}'::text[]             | NO             |
| 1_SCHEMA | marketplace_products      | price_cents            | integer                  | NO          | 0                        | NO             |
| 1_SCHEMA | marketplace_products      | currency               | text                     | YES         | 'USD'::text              | NO             |
| 1_SCHEMA | marketplace_products      | thumbnail_path         | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_products      | preview_images         | ARRAY                    | YES         | '{}'::text[]             | NO             |
| 1_SCHEMA | marketplace_products      | download_count         | integer                  | YES         | 0                        | NO             |
| 1_SCHEMA | marketplace_products      | rating_avg             | numeric                  | YES         | 0                        | NO             |
| 1_SCHEMA | marketplace_products      | rating_count           | integer                  | YES         | 0                        | NO             |
| 1_SCHEMA | marketplace_products      | status                 | text                     | YES         | 'draft'::text            | NO             |
| 1_SCHEMA | marketplace_products      | featured               | boolean                  | YES         | false                    | NO             |
| 1_SCHEMA | marketplace_products      | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | marketplace_products      | updated_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | marketplace_products      | polar_product_id       | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_products      | polar_benefit_id       | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_products      | storage_path           | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_purchases     | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | marketplace_purchases     | user_id                | uuid                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_purchases     | product_id             | uuid                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_purchases     | price_paid_cents       | integer                  | YES         | 0                        | NO             |
| 1_SCHEMA | marketplace_purchases     | license_key            | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_purchases     | status                 | text                     | YES         | 'completed'::text        | NO             |
| 1_SCHEMA | marketplace_purchases     | download_count         | integer                  | YES         | 0                        | NO             |
| 1_SCHEMA | marketplace_purchases     | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | marketplace_purchases     | polar_order_id         | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_ratings       | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | marketplace_ratings       | user_id                | uuid                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_ratings       | product_id             | uuid                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_ratings       | rating                 | integer                  | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_ratings       | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | marketplace_ratings       | updated_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | marketplace_sections      | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | marketplace_sections      | slug                   | text                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_sections      | type                   | text                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_sections      | title                  | text                     | NO          | null                     | NO             |
| 1_SCHEMA | marketplace_sections      | position               | integer                  | NO          | 0                        | NO             |
| 1_SCHEMA | marketplace_sections      | slides                 | jsonb                    | YES         | '[]'::jsonb              | NO             |
| 1_SCHEMA | marketplace_sections      | algorithm              | jsonb                    | YES         | '{}'::jsonb              | NO             |
| 1_SCHEMA | marketplace_sections      | creator_name           | text                     | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_sections      | product_ids            | ARRAY                    | YES         | '{}'::uuid[]             | NO             |
| 1_SCHEMA | marketplace_sections      | collections            | jsonb                    | YES         | '[]'::jsonb              | NO             |
| 1_SCHEMA | marketplace_sections      | is_active              | boolean                  | YES         | true                     | NO             |
| 1_SCHEMA | marketplace_sections      | starts_at              | timestamp with time zone | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_sections      | expires_at             | timestamp with time zone | YES         | null                     | NO             |
| 1_SCHEMA | marketplace_sections      | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | marketplace_sections      | updated_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | subscriptions             | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | subscriptions             | user_id                | uuid                     | YES         | null                     | NO             |
| 1_SCHEMA | subscriptions             | stripe_customer_id     | text                     | YES         | null                     | NO             |
| 1_SCHEMA | subscriptions             | stripe_subscription_id | text                     | YES         | null                     | NO             |
| 1_SCHEMA | subscriptions             | plan                   | text                     | YES         | 'free'::text             | NO             |
| 1_SCHEMA | subscriptions             | status                 | text                     | YES         | 'active'::text           | NO             |
| 1_SCHEMA | subscriptions             | current_period_end     | timestamp with time zone | YES         | null                     | NO             |
| 1_SCHEMA | subscriptions             | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | subscriptions             | updated_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | user_activity             | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | user_activity             | user_id                | uuid                     | YES         | null                     | NO             |
| 1_SCHEMA | user_activity             | event                  | text                     | NO          | null                     | NO             |
| 1_SCHEMA | user_activity             | addon_version          | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_activity             | blender_version        | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_activity             | platform               | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_activity             | country                | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_activity             | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | user_profiles             | id                     | uuid                     | NO          | null                     | YES            |
| 1_SCHEMA | user_profiles             | email                  | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_profiles             | display_name           | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_profiles             | avatar_url             | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_profiles             | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | user_profiles             | updated_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | user_profiles             | polar_customer_id      | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_sessions             | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | user_sessions             | user_id                | uuid                     | YES         | null                     | NO             |
| 1_SCHEMA | user_sessions             | session_id             | text                     | NO          | null                     | NO             |
| 1_SCHEMA | user_sessions             | device_info            | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_sessions             | host_app               | text                     | YES         | null                     | NO             |
| 1_SCHEMA | user_sessions             | created_at             | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | user_sessions             | last_active_at         | timestamp with time zone | YES         | now()                    | NO             |
| 1_SCHEMA | webhook_logs              | id                     | uuid                     | NO          | gen_random_uuid()        | YES            |
| 1_SCHEMA | webhook_logs              | event_type             | text                     | YES         | null                     | NO             |
| 1_SCHEMA | webhook_logs              | payload                | jsonb                    | YES         | null                     | NO             |
| 1_SCHEMA | webhook_logs              | status                 | text                     | YES         | 'received'::text         | NO             |
| 1_SCHEMA | webhook_logs              | error                  | text                     | YES         | null                     | NO             |
| 1_SCHEMA | webhook_logs              | created_at             | timestamp with time zone | YES         | now()                    | NO             |

-- 2. FOREIGN KEY RELATIONSHIPS

| section         | from_table            | from_column | to_table             | to_column | constraint_name                       |
| --------------- | --------------------- | ----------- | -------------------- | --------- | ------------------------------------- |
| 2_RELATIONSHIPS | marketplace_purchases | product_id  | marketplace_products | id        | marketplace_purchases_product_id_fkey |
| 2_RELATIONSHIPS | marketplace_ratings   | product_id  | marketplace_products | id        | marketplace_ratings_product_id_fkey   |
| 2_RELATIONSHIPS | subscriptions         | user_id     | user_profiles        | id        | subscriptions_user_id_fkey            |
| 2_RELATIONSHIPS | user_activity         | user_id     | user_profiles        | id        | user_activity_user_id_fkey            |
| 2_RELATIONSHIPS | user_sessions         | user_id     | user_profiles        | id        | user_sessions_user_id_fkey            |

-- 3. ROW LEVEL SECURITY (RLS) POLICIES

| section        | schemaname | tablename                 | policyname                         | permissive | roles           | operation | using_expression                                                                                                 | with_check_expression  |
| -------------- | ---------- | ------------------------- | ---------------------------------- | ---------- | --------------- | --------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------- |
| 3_RLS_POLICIES | public     | marketplace_feature_flags | Anyone can read flags              | PERMISSIVE | {public}        | SELECT    | true                                                                                                             | null                   |
| 3_RLS_POLICIES | public     | marketplace_products      | Anyone can read published products | PERMISSIVE | {public}        | SELECT    | (status = 'published'::text)                                                                                     | null                   |
| 3_RLS_POLICIES | public     | marketplace_purchases     | Users read own purchases           | PERMISSIVE | {public}        | SELECT    | (auth.uid() = user_id)                                                                                           | null                   |
| 3_RLS_POLICIES | public     | marketplace_ratings       | Anyone can read ratings            | PERMISSIVE | {public}        | SELECT    | true                                                                                                             | null                   |
| 3_RLS_POLICIES | public     | marketplace_ratings       | Users can delete own ratings       | PERMISSIVE | {public}        | DELETE    | (auth.uid() = user_id)                                                                                           | null                   |
| 3_RLS_POLICIES | public     | marketplace_ratings       | Users can insert own ratings       | PERMISSIVE | {public}        | INSERT    | null                                                                                                             | (auth.uid() = user_id) |
| 3_RLS_POLICIES | public     | marketplace_ratings       | Users can update own ratings       | PERMISSIVE | {public}        | UPDATE    | (auth.uid() = user_id)                                                                                           | (auth.uid() = user_id) |
| 3_RLS_POLICIES | public     | marketplace_sections      | Anyone can read active sections    | PERMISSIVE | {public}        | SELECT    | (is_active AND ((starts_at IS NULL) OR (starts_at <= now())) AND ((expires_at IS NULL) OR (expires_at > now()))) | null                   |
| 3_RLS_POLICIES | public     | subscriptions             | Users can read own subscription    | PERMISSIVE | {public}        | SELECT    | (auth.uid() = user_id)                                                                                           | null                   |
| 3_RLS_POLICIES | public     | user_activity             | Users can insert own activity      | PERMISSIVE | {public}        | INSERT    | null                                                                                                             | (auth.uid() = user_id) |
| 3_RLS_POLICIES | public     | user_activity             | Users can read own activity        | PERMISSIVE | {public}        | SELECT    | (auth.uid() = user_id)                                                                                           | null                   |
| 3_RLS_POLICIES | public     | user_profiles             | Users can insert their own profile | PERMISSIVE | {authenticated} | INSERT    | null                                                                                                             | (auth.uid() = id)      |
| 3_RLS_POLICIES | public     | user_profiles             | Users can read own profile         | PERMISSIVE | {public}        | SELECT    | (auth.uid() = id)                                                                                                | null                   |
| 3_RLS_POLICIES | public     | user_profiles             | Users can update own profile       | PERMISSIVE | {public}        | UPDATE    | (auth.uid() = id)                                                                                                | null                   |
| 3_RLS_POLICIES | public     | user_sessions             | Users can delete own sessions      | PERMISSIVE | {public}        | DELETE    | (auth.uid() = user_id)                                                                                           | null                   |
| 3_RLS_POLICIES | public     | user_sessions             | Users can insert own sessions      | PERMISSIVE | {public}        | INSERT    | null                                                                                                             | (auth.uid() = user_id) |
| 3_RLS_POLICIES | public     | user_sessions             | Users can manage own sessions      | PERMISSIVE | {public}        | ALL       | (auth.uid() = user_id)                                                                                           | (auth.uid() = user_id) |
| 3_RLS_POLICIES | public     | user_sessions             | Users can read own sessions        | PERMISSIVE | {public}        | SELECT    | (auth.uid() = user_id)                                                                                           | null                   |
| 3_RLS_POLICIES | public     | user_sessions             | Users can update own sessions      | PERMISSIVE | {public}        | UPDATE    | (auth.uid() = user_id)                                                                                           | null                   |

-- 4. INDEXES

| section   | tablename                 | indexname                                    | indexdef                                                                                                                           |
| --------- | ------------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 4_INDEXES | marketplace_feature_flags | marketplace_feature_flags_pkey               | CREATE UNIQUE INDEX marketplace_feature_flags_pkey ON public.marketplace_feature_flags USING btree (key)                           |
| 4_INDEXES | marketplace_products      | marketplace_products_pkey                    | CREATE UNIQUE INDEX marketplace_products_pkey ON public.marketplace_products USING btree (id)                                      |
| 4_INDEXES | marketplace_products      | marketplace_products_slug_key                | CREATE UNIQUE INDEX marketplace_products_slug_key ON public.marketplace_products USING btree (slug)                                |
| 4_INDEXES | marketplace_purchases     | marketplace_purchases_pkey                   | CREATE UNIQUE INDEX marketplace_purchases_pkey ON public.marketplace_purchases USING btree (id)                                    |
| 4_INDEXES | marketplace_purchases     | marketplace_purchases_user_id_product_id_key | CREATE UNIQUE INDEX marketplace_purchases_user_id_product_id_key ON public.marketplace_purchases USING btree (user_id, product_id) |
| 4_INDEXES | marketplace_ratings       | marketplace_ratings_pkey                     | CREATE UNIQUE INDEX marketplace_ratings_pkey ON public.marketplace_ratings USING btree (id)                                        |
| 4_INDEXES | marketplace_ratings       | marketplace_ratings_user_id_product_id_key   | CREATE UNIQUE INDEX marketplace_ratings_user_id_product_id_key ON public.marketplace_ratings USING btree (user_id, product_id)     |
| 4_INDEXES | marketplace_sections      | marketplace_sections_pkey                    | CREATE UNIQUE INDEX marketplace_sections_pkey ON public.marketplace_sections USING btree (id)                                      |
| 4_INDEXES | marketplace_sections      | marketplace_sections_slug_key                | CREATE UNIQUE INDEX marketplace_sections_slug_key ON public.marketplace_sections USING btree (slug)                                |
| 4_INDEXES | subscriptions             | subscriptions_pkey                           | CREATE UNIQUE INDEX subscriptions_pkey ON public.subscriptions USING btree (id)                                                    |
| 4_INDEXES | subscriptions             | subscriptions_user_id_key                    | CREATE UNIQUE INDEX subscriptions_user_id_key ON public.subscriptions USING btree (user_id)                                        |
| 4_INDEXES | user_activity             | user_activity_pkey                           | CREATE UNIQUE INDEX user_activity_pkey ON public.user_activity USING btree (id)                                                    |
| 4_INDEXES | user_profiles             | profiles_pkey                                | CREATE UNIQUE INDEX profiles_pkey ON public.user_profiles USING btree (id)                                                         |
| 4_INDEXES | user_sessions             | user_sessions_pkey                           | CREATE UNIQUE INDEX user_sessions_pkey ON public.user_sessions USING btree (id)                                                    |
| 4_INDEXES | webhook_logs              | webhook_logs_pkey                            | CREATE UNIQUE INDEX webhook_logs_pkey ON public.webhook_logs USING btree (id)                                                      |

-- 5. DATABASE FUNCTIONS

| section     | routine_name          | routine_type | return_type | routine_definition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ----------- | --------------------- | ------------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 5_FUNCTIONS | handle_new_user       | FUNCTION     | trigger     | 
BEGIN
    INSERT INTO public.user_profiles (id, email, display_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name'),
        COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
                                                                                                                                                                     |
| 5_FUNCTIONS | update_product_rating | FUNCTION     | trigger     | 
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
 |

-- 6. TRIGGERS

| section    | trigger_name              | event  | table_name          | timing | action_statement                         |
| ---------- | ------------------------- | ------ | ------------------- | ------ | ---------------------------------------- |
| 6_TRIGGERS | trg_update_product_rating | INSERT | marketplace_ratings | AFTER  | EXECUTE FUNCTION update_product_rating() |
| 6_TRIGGERS | trg_update_product_rating | DELETE | marketplace_ratings | AFTER  | EXECUTE FUNCTION update_product_rating() |
| 6_TRIGGERS | trg_update_product_rating | UPDATE | marketplace_ratings | AFTER  | EXECUTE FUNCTION update_product_rating() |

-- 7. STORAGE BUCKETS

| section   | bucket_id              | name                   | public | file_size_limit | allowed_mime_types                             | created_at                    |
| --------- | ---------------------- | ---------------------- | ------ | --------------- | ---------------------------------------------- | ----------------------------- |
| 7_STORAGE | marketplace-assets     | marketplace-assets     | false  | 1073741824      | ["application/zip","application/octet-stream"] | 2026-03-06 16:00:28.126466+00 |
| 7_STORAGE | marketplace-thumbnails | marketplace-thumbnails | true   | 2097152         | ["image/png","image/jpeg","image/webp"]        | 2026-03-06 15:59:30.376225+00 |

-- 8. AUTH CONFIG (non-sensitive)

| section              | total_users | confirmed_users | active_last_30_days |
| -------------------- | ----------- | --------------- | ------------------- |
| 8_AUTH_USERS_SUMMARY | 5           | 5               | 5                   |