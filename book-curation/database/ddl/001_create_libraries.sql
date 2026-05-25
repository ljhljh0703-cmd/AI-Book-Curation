CREATE SCHEMA IF NOT EXISTS book;

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS book.libraries (
    id BIGSERIAL PRIMARY KEY,
    lib_code VARCHAR(50) NOT NULL UNIQUE,
    lib_name VARCHAR(255) NOT NULL,
    address VARCHAR(500),
    operating_time VARCHAR(500),
    closed VARCHAR(500),
    book_count INTEGER,
    latitude NUMERIC(10, 7),
    longitude NUMERIC(10, 7),
    location GEOGRAPHY(POINT, 4326),
    raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_libraries_lib_code ON book.libraries (lib_code);
CREATE INDEX IF NOT EXISTS idx_libraries_location ON book.libraries USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_libraries_lib_name ON book.libraries (lib_name);

CREATE OR REPLACE FUNCTION book.set_library_location()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude::DOUBLE PRECISION, NEW.latitude::DOUBLE PRECISION), 4326)::GEOGRAPHY;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_library_location ON book.libraries;
CREATE TRIGGER trg_set_library_location
BEFORE INSERT OR UPDATE OF latitude, longitude
ON book.libraries
FOR EACH ROW
EXECUTE FUNCTION book.set_library_location();
