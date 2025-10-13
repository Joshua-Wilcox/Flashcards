-- Add optional academic year grouping to modules
ALTER TABLE public.modules
    ADD COLUMN IF NOT EXISTS year integer;

COMMENT ON COLUMN public.modules.year IS 'Nullable academic year grouping for flashcard module selector UI.';
