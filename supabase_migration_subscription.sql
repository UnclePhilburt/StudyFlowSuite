-- Migration: Add subscription tracking fields for Scholar's Club
-- Run this in Supabase SQL Editor

-- Add subscription_status column (tracks Stripe subscription state)
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'inactive'
CHECK (subscription_status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid', 'inactive'));

-- Add stripe_subscription_id column (stores Stripe subscription ID)
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

-- Add index for faster Stripe customer lookups
CREATE INDEX IF NOT EXISTS user_profiles_stripe_customer_idx
ON user_profiles(stripe_customer_id);

-- Update existing users: if they have subscription_tier = 'pro', set status to 'active'
UPDATE user_profiles
SET subscription_status = 'active'
WHERE subscription_tier = 'pro' AND subscription_status = 'inactive';

-- Update existing free users to have proper status
UPDATE user_profiles
SET subscription_status = 'inactive'
WHERE subscription_tier = 'free' AND subscription_status IS NULL;
