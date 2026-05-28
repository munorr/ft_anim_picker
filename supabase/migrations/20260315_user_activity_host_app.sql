-- Add host_app column to user_activity (tracks blender vs maya)
ALTER TABLE user_activity ADD COLUMN IF NOT EXISTS host_app TEXT;
