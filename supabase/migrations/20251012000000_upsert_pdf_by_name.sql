-- Migration to handle PDF uploads with metadata names instead of IDs
-- This simplifies external API clients like n8n

-- Create a powerful RPC function to handle the "get-or-create" logic for all metadata
CREATE OR REPLACE FUNCTION upsert_pdf_with_metadata(
    p_storage_path text,
    p_original_filename text,
    p_file_size bigint,
    p_mime_type text,
    p_uploaded_by text,
    p_metadata jsonb,
    p_module_name text,
    p_topic_names text[],
    p_subtopic_names text[],
    p_tag_names text[]
)
RETURNS integer AS $$
DECLARE
    v_module_id integer;
    v_topic_ids integer[];
    v_subtopic_ids integer[];
    v_tag_ids integer[];
    v_pdf_id integer;
    topic_name text;
    subtopic_name text;
    tag_name text;
BEGIN
    -- 1. Get or create Module ID
    INSERT INTO modules (name) VALUES (p_module_name)
    ON CONFLICT (name) DO NOTHING;
    SELECT id INTO v_module_id FROM modules WHERE name = p_module_name;

    -- 2. Get or create Topic IDs
    IF p_topic_names IS NOT NULL AND array_length(p_topic_names, 1) > 0 THEN
        FOREACH topic_name IN ARRAY p_topic_names
        LOOP
            INSERT INTO topics (name, module_id) VALUES (topic_name, v_module_id)
            ON CONFLICT (name, module_id) DO NOTHING;
            
            v_topic_ids := array_append(v_topic_ids, (SELECT id FROM topics WHERE name = topic_name AND module_id = v_module_id));
        END LOOP;
    END IF;

    -- 3. Get or create Sub-Topic IDs
    IF p_subtopic_names IS NOT NULL AND array_length(p_subtopic_names, 1) > 0 THEN
        FOREACH subtopic_name IN ARRAY p_subtopic_names
        LOOP
            INSERT INTO subtopics (name) VALUES (subtopic_name)
            ON CONFLICT (name) DO NOTHING;
            
            v_subtopic_ids := array_append(v_subtopic_ids, (SELECT id FROM subtopics WHERE name = subtopic_name));
        END LOOP;
    END IF;

    -- 4. Get or create Tag IDs (ensuring global uniqueness)
    IF p_tag_names IS NOT NULL AND array_length(p_tag_names, 1) > 0 THEN
        FOREACH tag_name IN ARRAY p_tag_names
        LOOP
            INSERT INTO tags (name) VALUES (tag_name)
            ON CONFLICT (name) DO NOTHING;
            
            v_tag_ids := array_append(v_tag_ids, (SELECT id FROM tags WHERE name = tag_name));
        END LOOP;
    END IF;

    -- 5. Insert the PDF record
    INSERT INTO pdfs (storage_path, original_filename, file_size, mime_type, uploaded_by, metadata, module_id, is_active)
    VALUES (p_storage_path, p_original_filename, p_file_size, p_mime_type, p_uploaded_by, p_metadata, v_module_id, true)
    RETURNING id INTO v_pdf_id;

    -- 6. Link the PDF to its topics, subtopics, and tags
    IF v_topic_ids IS NOT NULL THEN
        INSERT INTO pdf_topics (pdf_id, topic_id)
        SELECT v_pdf_id, unnest(v_topic_ids);
    END IF;

    IF v_subtopic_ids IS NOT NULL THEN
        INSERT INTO pdf_subtopics (pdf_id, subtopic_id)
        SELECT v_pdf_id, unnest(v_subtopic_ids);
    END IF;

    IF v_tag_ids IS NOT NULL THEN
        INSERT INTO pdf_tags (pdf_id, tag_id)
        SELECT v_pdf_id, unnest(v_tag_ids);
    END IF;

    RETURN v_pdf_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION upsert_pdf_with_metadata(text, text, bigint, text, text, jsonb, text, text[], text[], text[]) IS 
'Handles the complete insertion of a PDF and its metadata by name. It gets or creates modules, topics, subtopics, and tags, then links them to the new PDF record, returning the new PDF ID.';
