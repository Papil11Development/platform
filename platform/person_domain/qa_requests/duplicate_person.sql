CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
DECLARE
    workspace_id UUID := %s;

    -- PERSON INFO
    profile_info TEXT := %s;
    group_ids UUID[] := %s;

    -- ACTIVITY DATA
    activity_data TEXT := %s;
    camera_id UUID := %s;

    -- BLOB DATA
    face_img_meta TEXT := %s;
    face_img_binary_data BYTEA := %s;

    body_v1_meta TEXT := %s;
    body_v1_binary_data BYTEA := %s;
    body_bs_meta TEXT := %s;
    body_bs_binary_data BYTEA := %s;

    sample_img_meta TEXT := %s;
    sample_img_binary_data BYTEA := %s;
    face_bs_meta TEXT := %s;
    face_bs_binary_data BYTEA := %s;
    face_template_meta TEXT := %s;
    face_template_binary_data BYTEA := %s;

    -- SAMPLE DATA
    sample_meta TEXT := %s;

    duplicate_count INT := %s;

    fast_mode BOOLEAN := %s;

    i INT;
    sample_id UUID;
    face_img_blob_id UUID;
    face_img_blob_meta_id UUID;

    body_v1_blob_id UUID;
    body_v1_blob_meta_id UUID;
    body_bs_blob_id UUID;
    body_bs_blob_meta_id UUID;

    sample_img_blob_id UUID;
    sample_img_blob_meta_id UUID;
    face_bs_blob_id UUID;
    face_bs_blob_meta_id UUID;
    face_template_blob_id UUID;
    face_template_blob_meta_id UUID;

    person_id UUID;
    profile_id UUID;
    activity_id UUID;
    group_id UUID;
    text_activity_id TEXT;

    new_profile_info TEXT;
    new_activity_data TEXT;
    new_face_img_meta TEXT;
    new_face_template_meta TEXT;
    new_face_bs_meta TEXT;
    new_body_v1_meta TEXT;
    new_body_bs_meta TEXT;
    new_sample_meta TEXT;

BEGIN
     FOR i in 1..duplicate_count LOOP
        -- for proper blob meta info
        activity_id :=  uuid_generate_v4();

        IF (fast_mode IS FALSE) THEN
            -- ************************ BLOB, BLOBMETA ***************************
            -- meta activity_id update
            new_face_img_meta := replace(face_img_meta, '[activity_id]', activity_id::text);
            new_face_template_meta := replace(face_template_meta, '[activity_id]', activity_id::text);
            new_face_bs_meta := replace(face_bs_meta, '[activity_id]', activity_id::text);

            -- face $binary_image
            face_img_blob_id :=  uuid_generate_v4();

            IF (face_img_meta IS NOT NULL) THEN
                INSERT INTO data_domain_blob ("id", "data", "creation_date", "last_modified")
                    VALUES (face_img_blob_id, face_img_binary_data, current_timestamp, current_timestamp);

                face_img_blob_meta_id :=  uuid_generate_v4();

                INSERT INTO data_domain_blobmeta ("id", "meta", "creation_date", "last_modified", "blob_id", "workspace_id")
                    VALUES (face_img_blob_meta_id, cast(new_face_img_meta AS json), current_timestamp, current_timestamp, face_img_blob_id, workspace_id);
            END IF;

            -- face $template from sample
            face_template_blob_id :=  uuid_generate_v4();

            INSERT INTO data_domain_blob ("id", "data", "creation_date", "last_modified")
                VALUES (face_template_blob_id, face_template_binary_data, current_timestamp, current_timestamp);

            face_template_blob_meta_id :=  uuid_generate_v4();

            INSERT INTO data_domain_blobmeta ("id", "meta", "creation_date", "last_modified", "blob_id", "workspace_id")
                VALUES (face_template_blob_meta_id, cast(new_face_template_meta AS json), current_timestamp, current_timestamp, face_template_blob_id, workspace_id);

            -- face best shot
            face_bs_blob_id :=  uuid_generate_v4();
            face_bs_blob_meta_id :=  uuid_generate_v4();
            IF (face_bs_meta IS NOT NULL) THEN
                -- from activity ($best_shot)
                INSERT INTO data_domain_blob ("id", "data", "creation_date", "last_modified")
                    VALUES (face_bs_blob_id, face_bs_binary_data, current_timestamp, current_timestamp);
                INSERT INTO data_domain_blobmeta ("id", "meta", "creation_date", "last_modified", "blob_id", "workspace_id")
                    VALUES (face_bs_blob_meta_id, cast(new_face_bs_meta AS json), current_timestamp, current_timestamp, face_bs_blob_id, workspace_id);
            ELSE
                -- from sample ($crop_image)
                INSERT INTO data_domain_blob ("id", "data", "creation_date", "last_modified")
                    VALUES (face_bs_blob_id, sample_crop_binary_data, current_timestamp, current_timestamp);
                INSERT INTO data_domain_blobmeta ("id", "meta", "creation_date", "last_modified", "blob_id", "workspace_id")
                    VALUES (face_bs_blob_meta_id, cast(sample_crop_meta AS json), current_timestamp, current_timestamp, face_bs_blob_id, workspace_id);
            END IF;

            IF (body_v1_meta IS NOT NULL) AND (body_bs_meta IS NOT NULL) THEN

                -- meta activity_id update
                new_body_v1_meta := replace(body_v1_meta, '[activity_id]', activity_id::text);
                new_body_bs_meta := replace(body_bs_meta, '[activity_id]', activity_id::text);

                -- body v1
                body_v1_blob_id :=  uuid_generate_v4();

                INSERT INTO data_domain_blob ("id", "data", "creation_date", "last_modified")
                    VALUES (body_v1_blob_id, body_v1_binary_data, current_timestamp, current_timestamp);

                body_v1_blob_meta_id :=  uuid_generate_v4();

                INSERT INTO data_domain_blobmeta ("id", "meta", "creation_date", "last_modified", "blob_id", "workspace_id")
                    VALUES (body_v1_blob_meta_id, cast(new_body_v1_meta AS json), current_timestamp, current_timestamp, body_v1_blob_id, workspace_id);

                -- body best shot
                body_bs_blob_id :=  uuid_generate_v4();

                INSERT INTO data_domain_blob ("id", "data", "creation_date", "last_modified")
                    VALUES (body_bs_blob_id, body_bs_binary_data, current_timestamp, current_timestamp);

                body_bs_blob_meta_id :=  uuid_generate_v4();

                INSERT INTO data_domain_blobmeta ("id", "meta", "creation_date", "last_modified", "blob_id", "workspace_id")
                    VALUES (body_bs_blob_meta_id, cast(new_body_bs_meta AS json), current_timestamp, current_timestamp, body_bs_blob_id, workspace_id);
            END IF;

            -- sample $image
            sample_img_blob_id :=  uuid_generate_v4();
            sample_img_blob_meta_id :=  uuid_generate_v4();
            IF (sample_img_meta IS NOT NULL) THEN
                INSERT INTO data_domain_blob ("id", "data", "creation_date", "last_modified")
                    VALUES (sample_img_blob_id, sample_img_binary_data, current_timestamp, current_timestamp);
                INSERT INTO data_domain_blobmeta ("id", "meta", "creation_date", "last_modified", "blob_id", "workspace_id")
                    VALUES (sample_img_blob_meta_id, cast(sample_img_meta AS json), current_timestamp, current_timestamp, sample_img_blob_id, workspace_id);
            END IF;

        END IF;
        -- **************************** SAMPLE *******************************
        -- for proper sample meta
        person_id :=  uuid_generate_v4();

        -- main sample creation
        sample_id :=  uuid_generate_v4();

        new_sample_meta := replace(sample_meta, '[person_id]', person_id::text);

        IF (fast_mode IS FALSE) THEN
            new_sample_meta := replace(new_sample_meta, '[sample_template]', face_template_blob_meta_id::text);
            new_sample_meta := replace(new_sample_meta, '[sample_image]', sample_img_blob_meta_id::text);
            new_sample_meta := replace(new_sample_meta, '[sample_crop_image]', face_bs_blob_meta_id::text);
        END IF;

        INSERT INTO data_domain_sample ("id", "meta", "creation_date", "last_modified", "workspace_id")
            VALUES (sample_id, cast(new_sample_meta AS json), current_timestamp, current_timestamp, workspace_id);

        -- ************************ Person, Profile ***************************
        INSERT INTO person_domain_person ("id", "creation_date", "last_modified", "workspace_id")
            VALUES (person_id, current_timestamp, current_timestamp, workspace_id);

        profile_id := uuid_generate_v4();

        new_profile_info := replace(profile_info, '[main_sample_id]', sample_id::text);
        new_profile_info := replace(new_profile_info, '[avatar_id]', face_bs_blob_meta_id::text);

        INSERT INTO person_domain_profile ("id", "info", "last_modified", "creation_date", "person_id", "workspace_id")
            VALUES (profile_id, cast(new_profile_info AS json), current_timestamp, current_timestamp, person_id, workspace_id);

        INSERT INTO person_domain_profile_samples ("profile_id", "sample_id")
            VALUES (profile_id, sample_id);

        FOREACH group_id in ARRAY group_ids LOOP
            INSERT INTO person_domain_profilegroup ("id", "label_id", "profile_id")
                VALUES (uuid_generate_v4(), group_id, profile_id);
        END LOOP;

        -- ************************ Activity ***************************
        IF (activity_data IS NOT NULL) THEN

            new_activity_data := replace(activity_data, '[person_id]', person_id::text);

            IF (fast_mode IS FALSE) THEN
                new_activity_data := replace(new_activity_data, '[face_binary_image]', face_img_blob_meta_id::text);
                new_activity_data := replace(new_activity_data, '[face_template]', face_template_blob_meta_id::text);
                new_activity_data := replace(new_activity_data, '[face_best_shot]', face_bs_blob_meta_id::text);

                IF (body_v1_meta IS NOT NULL) AND (body_bs_meta IS NOT NULL) THEN
                    new_activity_data := replace(new_activity_data, '[body_v1]', body_v1_blob_meta_id::text);
                    new_activity_data := replace(new_activity_data, '[body_best_shot]', body_bs_blob_meta_id::text);
                END IF;
            END IF;

            INSERT INTO data_domain_activity ("id", "data", "creation_date", "last_modified", "camera_id", "person_id", "workspace_id")
                VALUES (activity_id, cast(new_activity_data AS json), current_timestamp, current_timestamp, camera_id, person_id, workspace_id);
        END IF;

     END LOOP;
END $$;
