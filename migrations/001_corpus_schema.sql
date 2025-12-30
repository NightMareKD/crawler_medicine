-- Migration 001: Corpus Schema Extensions
-- Adds language annotation, Q&A pairs, bias tracking, and versioning support

-- =============================================
-- 1. Extend raw_ingest table with language/annotation columns
-- =============================================

ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS detected_language TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS language_confidence FLOAT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS is_romanized BOOLEAN DEFAULT FALSE;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS romanized_type TEXT; -- 'singlish', 'tamilish', 'english', null
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS translated_text JSONB DEFAULT '{}'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS entities JSONB DEFAULT '[]'::jsonb;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS intent TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE raw_ingest ADD COLUMN IF NOT EXISTS region TEXT;

-- =============================================
-- 2. Q&A Pairs Table
-- =============================================

CREATE TABLE IF NOT EXISTS qa_pairs (
    id TEXT PRIMARY KEY,
    
    -- Question fields
    question_text TEXT NOT NULL,
    question_language TEXT,  -- 'sinhala', 'tamil', 'english'
    question_is_romanized BOOLEAN DEFAULT FALSE,
    question_romanized_type TEXT, -- 'singlish', 'tamilish', null
    
    -- Answer fields
    answer_text TEXT NOT NULL,
    answer_language TEXT,
    
    -- Annotations
    intent TEXT,
    domain TEXT,
    entities JSONB DEFAULT '[]'::jsonb,
    
    -- Source tracking
    source_context_id TEXT REFERENCES raw_ingest(id),
    source_url TEXT,
    
    -- Review status
    verified BOOLEAN DEFAULT FALSE,
    reviewer_id TEXT,
    review_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 3. Corpus Statistics Table (Bias Tracking)
-- =============================================

CREATE TABLE IF NOT EXISTS corpus_statistics (
    id TEXT PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    
    -- Counts
    total_documents INTEGER DEFAULT 0,
    total_qa_pairs INTEGER DEFAULT 0,
    
    -- Language distribution
    language_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"sinhala": 1200, "tamil": 800, "english": 2000, "romanized": 500}
    
    -- Romanized breakdown
    romanized_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"singlish": 300, "tamilish": 150, "mixed": 50}
    
    -- Region distribution
    region_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"colombo": 500, "kandy": 200, "rural": 100}
    
    -- Domain distribution  
    domain_distribution JSONB DEFAULT '{}'::jsonb,
    -- Example: {"dengue": 400, "mental_health": 150, "opd": 300}
    
    -- Intent distribution
    intent_distribution JSONB DEFAULT '{}'::jsonb,
    
    -- Bias flags
    bias_alerts JSONB DEFAULT '[]'::jsonb,
    -- Example: [{"type": "underrepresented", "category": "tamil", "severity": "high"}]
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 4. Content Versions Table (Deduplication)
-- =============================================

CREATE TABLE IF NOT EXISTS content_versions (
    id TEXT PRIMARY KEY,
    context_id TEXT REFERENCES raw_ingest(id),
    content_hash TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    previous_version_id TEXT,
    changes_summary TEXT,
    content_diff JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- 5. Indexes for Performance
-- =============================================

-- Language queries
CREATE INDEX IF NOT EXISTS idx_raw_ingest_language ON raw_ingest(detected_language);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_romanized ON raw_ingest(is_romanized) WHERE is_romanized = TRUE;
CREATE INDEX IF NOT EXISTS idx_raw_ingest_domain ON raw_ingest(domain);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_intent ON raw_ingest(intent);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_region ON raw_ingest(region);

-- Q&A queries
CREATE INDEX IF NOT EXISTS idx_qa_pairs_language ON qa_pairs(question_language);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_romanized ON qa_pairs(question_is_romanized) WHERE question_is_romanized = TRUE;
CREATE INDEX IF NOT EXISTS idx_qa_pairs_domain ON qa_pairs(domain);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_verified ON qa_pairs(verified);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_source ON qa_pairs(source_context_id);

-- Deduplication
CREATE INDEX IF NOT EXISTS idx_content_versions_hash ON content_versions(content_hash);
CREATE INDEX IF NOT EXISTS idx_content_versions_context ON content_versions(context_id);
CREATE INDEX IF NOT EXISTS idx_raw_ingest_hash ON raw_ingest(content_hash);

-- Statistics
CREATE INDEX IF NOT EXISTS idx_corpus_stats_date ON corpus_statistics(snapshot_date DESC);

-- =============================================
-- 6. Triggers for updated_at
-- =============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_qa_pairs_updated_at ON qa_pairs;
CREATE TRIGGER update_qa_pairs_updated_at
    BEFORE UPDATE ON qa_pairs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
