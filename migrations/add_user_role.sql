-- Migration: add role column to users table
-- Run this ONCE against any existing database that was created before the
-- role feature was added (the column is created automatically by SQLAlchemy
-- create_all only for brand-new tables).
--
-- Usage:
--   psql "$DATABASE_URL" -f migrations/add_user_role.sql

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';

-- To promote a specific user to admin, run:
--   UPDATE users SET role = 'admin' WHERE email = 'admin@example.com';
