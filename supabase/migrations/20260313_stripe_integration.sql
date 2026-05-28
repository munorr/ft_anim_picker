-- ============================================================================
-- Stripe Payment Integration
-- Adds Stripe customer/payment tracking columns to existing tables.
-- ============================================================================

-- 1. Stripe Customer ID on user_profiles
ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_stripe_customer
    ON user_profiles(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- 2. Stripe payment references on marketplace_purchases
ALTER TABLE marketplace_purchases
    ADD COLUMN IF NOT EXISTS stripe_checkout_session_id TEXT,
    ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT;

-- 3. Stripe payment reference on marketplace_transactions
ALTER TABLE marketplace_transactions
    ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT;
