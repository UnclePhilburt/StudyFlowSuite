-- Migration: Legal Compliance for Syllabus Feature
-- Allows NULL values for file_path and extracted_text to comply with:
-- - Copyright Law (17 USC 107 - Fair Use): Don't store copyrighted content
-- - Missouri SB 1324 (Privacy): Don't store original documents
-- - FERPA: Don't store student PII

-- =====================================================
-- Alter syllabi table to allow NULL for legal compliance
-- =====================================================

-- Allow NULL for file_path (we don't store original syllabus files)
ALTER TABLE syllabi ALTER COLUMN file_path DROP NOT NULL;

-- Allow NULL for extracted_text (we don't store copyrighted content)
ALTER TABLE syllabi ALTER COLUMN extracted_text DROP NOT NULL;

-- Add comments explaining legal compliance
COMMENT ON COLUMN syllabi.file_path IS 'NULL for legal compliance - original files are processed and discarded (SB 1324, Fair Use)';
COMMENT ON COLUMN syllabi.extracted_text IS 'NULL for legal compliance - copyrighted text is not stored (17 USC 107)';

-- =====================================================
-- The workflow is now:
-- 1. User uploads syllabus file
-- 2. Backend extracts text in memory
-- 3. AI extracts ONLY factual data (dates, times, task names)
-- 4. Calendar events are saved
-- 5. Original file and text are discarded (never stored)
-- =====================================================
