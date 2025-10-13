-- Add missing foreign key relationship between module_stats and user_stats
-- This will enable proper joins in Supabase PostgREST

-- First check if the constraint already exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_module_stats_user_stats'
        AND table_name = 'module_stats'
    ) THEN
        -- Add foreign key constraint
        ALTER TABLE module_stats 
        ADD CONSTRAINT fk_module_stats_user_stats 
        FOREIGN KEY (user_id) REFERENCES user_stats(user_id) ON DELETE CASCADE;
    END IF;
END $$;

-- Verify the constraint was added
SELECT 
    tc.constraint_name, 
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
WHERE 
    tc.constraint_type = 'FOREIGN KEY' 
    AND tc.table_name = 'module_stats'
    AND tc.constraint_name = 'fk_module_stats_user_stats';
