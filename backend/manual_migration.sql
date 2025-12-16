-- Manual SQL migration for SQLite database
-- Run these commands on your marketing_mvp.db file

-- Add retrieved_docs column to jobs table
ALTER TABLE jobs ADD COLUMN retrieved_docs JSON;

-- Add final_prompt column to jobs table
ALTER TABLE jobs ADD COLUMN final_prompt TEXT;

-- Verify the changes
.schema jobs
