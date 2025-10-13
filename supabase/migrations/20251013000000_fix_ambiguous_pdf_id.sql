-- Fix ambiguous pdf_id reference in upsert_pdf_with_metadata functions
-- Split the overloaded procedure into explicit name-based and id-based variants

DROP FUNCTION IF EXISTS upsert_pdf_with_metadata(text, text, bigint, text, text, jsonb, text, text[], text[], text[]);
DROP FUNCTION IF EXISTS upsert_pdf_with_metadata(text, text, integer, integer[], integer[], integer[], text, jsonb, bigint, text);

CREATE OR REPLACE FUNCTION upsert_pdf_with_metadata_by_ids(
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
    SELECT id INTO existing_pdf_id
    FROM pdfs 
    WHERE original_filename = original_filename_param 
      AND module_id = module_id_param 
      AND is_active = true;
    
    IF existing_pdf_id IS NOT NULL THEN
        UPDATE pdfs SET
            storage_path = storage_path_param,
            file_size = COALESCE(file_size_param, file_size),
            mime_type = COALESCE(mime_type_param, mime_type),
            metadata = metadata_param,
            uploaded_by = COALESCE(uploaded_by_param, uploaded_by)
        WHERE id = existing_pdf_id;
        
        new_pdf_id := existing_pdf_id;
        
        DELETE FROM pdf_topics WHERE pdf_id = existing_pdf_id;
        DELETE FROM pdf_subtopics WHERE pdf_id = existing_pdf_id;
        DELETE FROM pdf_tags WHERE pdf_id = existing_pdf_id;
        
    ELSE
        INSERT INTO pdfs (
            storage_path, original_filename, module_id, file_size, 
            mime_type, uploaded_by, metadata, is_active
        ) VALUES (
            storage_path_param, original_filename_param, module_id_param, 
            file_size_param, mime_type_param, uploaded_by_param, metadata_param, true
        ) RETURNING id INTO new_pdf_id;
    END IF;
    
    IF topic_ids_param IS NOT NULL THEN
        FOREACH topic_id IN ARRAY topic_ids_param
        LOOP
            INSERT INTO pdf_topics (pdf_id, topic_id) 
            VALUES (new_pdf_id, topic_id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;
    
    IF subtopic_ids_param IS NOT NULL THEN
        FOREACH subtopic_id IN ARRAY subtopic_ids_param
        LOOP
            INSERT INTO pdf_subtopics (pdf_id, subtopic_id) 
            VALUES (new_pdf_id, subtopic_id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;
    
    IF tag_ids_param IS NOT NULL THEN
        FOREACH tag_id IN ARRAY tag_ids_param
        LOOP
            INSERT INTO pdf_tags (pdf_id, tag_id, count) 
            VALUES (new_pdf_id, tag_id, 1)
            ON CONFLICT (pdf_id, tag_id) DO UPDATE SET count = pdf_tags.count + EXCLUDED.count;
        END LOOP;
    END IF;
    
    RETURN QUERY SELECT 
        true AS success, 
        new_pdf_id::integer AS pdf_id, 
        CASE 
            WHEN existing_pdf_id IS NOT NULL THEN 'PDF updated successfully'
            ELSE 'PDF created successfully'
        END AS message;
        
EXCEPTION WHEN OTHERS THEN
    RETURN QUERY SELECT 
        false AS success, 
        NULL::integer AS pdf_id, 
        SQLERRM AS message;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION upsert_pdf_with_metadata_by_ids(text, text, integer, integer[], integer[], integer[], text, jsonb, bigint, text) IS 
'Upsert PDF metadata using resolved IDs. Handles topic/subtopic/tag associations with conflict-safe inserts.';

CREATE OR REPLACE FUNCTION upsert_pdf_with_metadata_by_names(
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
) RETURNS TABLE (
    success boolean,
    pdf_id integer,
    message text
) AS $$
DECLARE
    v_module_id integer;
    v_topic_ids integer[] := ARRAY[]::integer[];
    v_subtopic_ids integer[] := ARRAY[]::integer[];
    v_tag_ids integer[] := ARRAY[]::integer[];
    topic_name text;
    subtopic_name text;
    tag_name text;
BEGIN
    IF p_module_name IS NULL OR TRIM(p_module_name) = '' THEN
        RETURN QUERY SELECT false, NULL::integer, 'Module name is required';
        RETURN;
    END IF;

    INSERT INTO modules (name) VALUES (p_module_name)
    ON CONFLICT (name) DO NOTHING;
    SELECT id INTO v_module_id FROM modules WHERE name = p_module_name;

    IF v_module_id IS NULL THEN
        RETURN QUERY SELECT false, NULL::integer, 'Unable to resolve module name';
        RETURN;
    END IF;

    IF p_topic_names IS NOT NULL THEN
        FOREACH topic_name IN ARRAY p_topic_names
        LOOP
            CONTINUE WHEN topic_name IS NULL OR TRIM(topic_name) = '';
            INSERT INTO topics (name) VALUES (topic_name)
            ON CONFLICT (name) DO NOTHING;
            v_topic_ids := array_append(v_topic_ids, (SELECT id FROM topics WHERE name = topic_name));
        END LOOP;
    END IF;

    IF p_subtopic_names IS NOT NULL THEN
        FOREACH subtopic_name IN ARRAY p_subtopic_names
        LOOP
            CONTINUE WHEN subtopic_name IS NULL OR TRIM(subtopic_name) = '';
            INSERT INTO subtopics (name) VALUES (subtopic_name)
            ON CONFLICT (name) DO NOTHING;
            v_subtopic_ids := array_append(v_subtopic_ids, (SELECT id FROM subtopics WHERE name = subtopic_name));
        END LOOP;
    END IF;

    IF p_tag_names IS NOT NULL THEN
        FOREACH tag_name IN ARRAY p_tag_names
        LOOP
            CONTINUE WHEN tag_name IS NULL OR TRIM(tag_name) = '';
            INSERT INTO tags (name) VALUES (tag_name)
            ON CONFLICT (name) DO NOTHING;
            v_tag_ids := array_append(v_tag_ids, (SELECT id FROM tags WHERE name = tag_name));
        END LOOP;
    END IF;

    RETURN QUERY
        SELECT * FROM upsert_pdf_with_metadata_by_ids(
            storage_path_param => p_storage_path,
            original_filename_param => p_original_filename,
            module_id_param => v_module_id,
            topic_ids_param => CASE WHEN array_length(v_topic_ids, 1) > 0 THEN v_topic_ids ELSE NULL END,
            subtopic_ids_param => CASE WHEN array_length(v_subtopic_ids, 1) > 0 THEN v_subtopic_ids ELSE NULL END,
            tag_ids_param => CASE WHEN array_length(v_tag_ids, 1) > 0 THEN v_tag_ids ELSE NULL END,
            uploaded_by_param => p_uploaded_by,
            metadata_param => COALESCE(p_metadata, '{}'::jsonb),
            file_size_param => p_file_size,
            mime_type_param => COALESCE(p_mime_type, 'application/pdf')
        );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION upsert_pdf_with_metadata_by_names(text, text, bigint, text, text, jsonb, text, text[], text[], text[]) IS 
'Resolve module/topic/subtopic/tag names before delegating to the ID-based PDF upsert procedure.';