-- Separate database for the pytest suite (tests need real Postgres: FOR UPDATE, DISTINCT ON).
CREATE DATABASE auction_test OWNER auction;
