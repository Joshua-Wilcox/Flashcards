-- Fix ambiguous pdf_id reference in upsert_pdf_with_metadata functions
-- There are two versions of this function with different signatures

-- Fix the name-based version (newer function)
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

    -- FIXED: Explicitly specify count column to avoid ambiguous column references
    IF v_tag_ids IS NOT NULL THEN
        INSERT INTO pdf_tags (pdf_id, tag_id, count)
        SELECT v_pdf_id, unnest(v_tag_ids), 1;
    END IF;

    RETURN v_pdf_id;
END;
$$ LANGUAGE plpgsql;

-- Fix the ID-based version (older function)  
CREATE OR REPLACE FUNCTION upsert_pdf_with_metadata(
    storage_path_param text,
    original_filename_param text,
    module_id_param integer,
    topic_ids_param integer[] DEFAULT NULL,
    subtopic_ids_param integer[] DEFAULT NULL,
    tag_ids_param integer[] DEFAULT NULL,
    uploaded_by_param text DEFAULT NULL,
    metadata_param jsonb DEFAULT '{}'::jsonb,
    file_size_param bigint DEFAULT NULL,
    mime_type_param text DEFAULT 'application/pdf'
) RETURNS TABLE (
    success boolean,
    pdf_id integer,
    message text
) AS $$
DECLARE
    existing_pdf_id integer;
    new_pdf_id integer;
    topic_id integer;
    subtopic_id integer;
    tag_id integer;
BEGIN
    -- Check for existing PDF with same filename and module
    SELECT id INTO existing_pdf_id
    FROM pdfs 
    WHERE original_filename = original_filename_param 
      AND module_id = module_id_param 
      AND is_active = true;
    
    IF existing_pdf_id IS NOT NULL THEN
        -- Update existing PDF
        UPDATE pdfs SET
            storage_path = storage_path_param,
            file_size = COALESCE(file_size_param, file_size),
            mime_type = COALESCE(mime_type_param, mime_type),
            metadata = metadata_param,
            uploaded_by = COALESCE(uploaded_by_param, uploaded_by)
        WHERE id = existing_pdf_id;
        
        new_pdf_id := existing_pdf_id;
        
        -- Clear existing associations
        DELETE FROM pdf_topics WHERE pdf_id = existing_pdf_id;
        DELETE FROM pdf_subtopics WHERE pdf_id = existing_pdf_id;
        DELETE FROM pdf_tags WHERE pdf_id = existing_pdf_id;
        
    ELSE
        -- Insert new PDF
        INSERT INTO pdfs (
            storage_path, original_filename, module_id, file_size, 
            mime_type, uploaded_by, metadata, is_active
        ) VALUES (
            storage_path_param, original_filename_param, module_id_param, 
            file_size_param, mime_type_param, uploaded_by_param, metadata_param, true
        ) RETURNING id INTO new_pdf_id;
    END IF;
    
    -- Insert topic associations
    IF topic_ids_param IS NOT NULL THEN
        FOREACH topic_id IN ARRAY topic_ids_param
        LOOP
            INSERT INTO pdf_topics (pdf_id, topic_id) 
            VALUES (new_pdf_id, topic_id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;
    
    -- Insert subtopic associations
    IF subtopic_ids_param IS NOT NULL THEN
        FOREACH subtopic_id IN ARRAY subtopic_ids_param
        LOOP
            INSERT INTO pdf_subtopics (pdf_id, subtopic_id) 
            VALUES (new_pdf_id, subtopic_id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;
    
    -- Insert tag associations (FIXED: Use EXCLUDED.count instead of ambiguous reference)
    IF tag_ids_param IS NOT NULL THEN
        FOREACH tag_id IN ARRAY tag_ids_param
        LOOP
            INSERT INTO pdf_tags (pdf_id, tag_id, count) 
            VALUES (new_pdf_id, tag_id, 1)
            ON CONFLICT (pdf_id, tag_id) DO UPDATE SET count = pdf_tags.count + EXCLUDED.count;
        END LOOP;
    END IF;
    
    RETURN QUERY SELECT 
        true as success, 
        new_pdf_id as pdf_id, 
        CASE 
            WHEN existing_pdf_id IS NOT NULL THEN 'PDF updated successfully'
            ELSE 'PDF created successfully'
        END as message;
        
EXCEPTION WHEN OTHERS THEN
    RETURN QUERY SELECT 
        false as success, 
        NULL::integer as pdf_id, 
        SQLERRM as message;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION upsert_pdf_with_metadata(text, text, bigint, text, text, jsonb, text, text[], text[], text[]) IS 
'Fixed name-based PDF upsert function with proper count column handling';

COMMENT ON FUNCTION upsert_pdf_with_metadata(text, text, integer, integer[], integer[], integer[], text, jsonb, bigint, text) IS 
'Fixed ID-based PDF upsert function with resolved ambiguous pdf_id reference';