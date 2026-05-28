-- Add optional review text to marketplace_ratings
ALTER TABLE marketplace_ratings ADD COLUMN IF NOT EXISTS review TEXT;
