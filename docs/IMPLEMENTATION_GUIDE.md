# Multilingual Health Corpus - Implementation Documentation

## Project: IT22919700 - Sri Lankan Health Information System

This document provides a complete technical reference for the 15-step implementation of the Multilingual Health Corpus project.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Step-by-Step Implementation](#step-by-step-implementation)
4. [API Reference](#api-reference)
5. [Database Schema](#database-schema)
6. [Usage Guide](#usage-guide)

---

## Overview

The Multilingual Health Corpus is a continuously-updated language dataset for Sri Lankan government health information. It supports:

- **4 Language Types**: Sinhala, Tamil, English, and Romanized (Singlish/Tamilish)
- **Deep Annotation**: Intent, domain, entities, language type
- **Q&A Pairs**: Question-answer extraction from health content
- **Bias Auditing**: Representation gap detection
- **Continuous Updates**: Automated 12-hour crawling schedule

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER                             │
├─────────────────────────────────────────────────────────────────┤
│  crawler_agent.py → asset_segregator.py → ocr_processor.py     │
│           ↓                                                      │
│      url_manager.py ←─────────→ supabase_repo.py                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     CORPUS LAYER (NEW)                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Language    │  │  Romanized   │  │  Translator  │          │
│  │  Detector    │→ │  Classifier  │→ │  (NLLB-200)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         ↓                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Text      │  │   Entity     │  │   Intent     │          │
│  │ Preprocessor │→ │  Extractor   │→ │  Classifier  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         ↓                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Domain     │  │     Q&A      │  │  Annotation  │          │
│  │   Tagger     │→ │  Generator   │→ │  Processor   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         ↓                                                        │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │    Bias      │  │  Content     │                             │
│  │   Auditor    │  │ Deduplicator │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     WEB LAYER (NEW)                             │
├─────────────────────────────────────────────────────────────────┤
│  FastAPI (web/app.py) → Dashboard, Review UI, Bias Reports     │
│  Scheduler (run_scheduled.py) → 12-hour automation             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Implementation

### Step 1: Project Structure & Schema Updates

**Goal**: Establish foundation with database migrations and package structure.

**Files Created**:
- `corpus/__init__.py` - Package initialization with all exports
- `migrations/001_corpus_schema.sql` - Database schema extensions
- `requirements.txt` - Updated dependencies
- `corpus/gazettes/health_entities.json` - Sri Lankan hospitals, diseases, symptoms
- `corpus/training_data/romanized_patterns.json` - Singlish/Tamilish markers

**New Database Tables**:
```sql
-- Extended raw_ingest
ALTER TABLE raw_ingest ADD COLUMN detected_language TEXT;
ALTER TABLE raw_ingest ADD COLUMN is_romanized BOOLEAN;
ALTER TABLE raw_ingest ADD COLUMN romanized_type TEXT;
ALTER TABLE raw_ingest ADD COLUMN entities JSONB;
ALTER TABLE raw_ingest ADD COLUMN intent TEXT;
ALTER TABLE raw_ingest ADD COLUMN domain TEXT;
ALTER TABLE raw_ingest ADD COLUMN content_hash TEXT;

-- New tables
CREATE TABLE qa_pairs (...);
CREATE TABLE corpus_statistics (...);
CREATE TABLE content_versions (...);
```

**New Dependencies**:
- `langdetect` - Language detection
- `transformers`, `torch`, `sentencepiece` - NLLB-200 translation
- `spacy` - NLP processing
- `fastapi`, `uvicorn`, `jinja2` - Web interface
- `schedule` - Task scheduling

---

### Step 2: Language Detection Module

**Goal**: Detect Sinhala, Tamil, English, and mixed-script content.

**File**: `corpus/language_detector.py`

**Key Features**:
- Unicode range detection:
  - Sinhala: U+0D80 to U+0DFF
  - Tamil: U+0B80 to U+0BFF
  - Latin: Basic ASCII letters
- Script distribution analysis
- `langdetect` fallback for Latin text

**Usage**:
```python
from corpus import LanguageDetector

detector = LanguageDetector()
result = detector.detect("මම ගෙදර යනවා")
# result.language = Language.SINHALA
# result.confidence = 0.95
# result.script_type = ScriptType.SINHALA_SCRIPT
```

---

### Step 3: Romanized Script Classifier

**Goal**: Classify Latin text as English, Singlish, or Tamilish.

**File**: `corpus/romanized_classifier.py`

**Key Features**:
- Singlish markers: `koheda`, `mokakda`, `mama`, `oya`, `ganna`, `yanna`, etc.
- Tamilish markers: `enga`, `eppo`, `naan`, `ponga`, `theriyuma`, etc.
- Code-switch detection for mixed content
- Loads patterns from `corpus/training_data/romanized_patterns.json`

**Usage**:
```python
from corpus import RomanizedClassifier

classifier = RomanizedClassifier()
result = classifier.classify("mage amma dengue clinic eka koheda")
# result.classification = RomanizedType.SINGLISH
# result.singlish_score = 0.6
# result.matched_markers = ["mage", "koheda"]
```

---

### Step 4: Translation Engine (NLLB-200)

**Goal**: Translate between Sinhala, Tamil, and English using GPU.

**File**: `corpus/translator.py`

**Key Features**:
- Model: `facebook/nllb-200-distilled-600M`
- GPU acceleration with CUDA support
- Language codes: `sin_Sinh`, `tam_Taml`, `eng_Latn`
- Lazy model loading
- Mock translator for testing

**Usage**:
```python
from corpus.translator import NLLBTranslator

translator = NLLBTranslator(device="cuda")
result = translator.translate(
    "Where is the hospital?",
    source_lang="english",
    target_lang="sinhala"
)
# result.translated_text = "රෝහල කොහෙද?"
```

---

### Step 5: Text Preprocessing Pipeline

**Goal**: Clean text and remove PII (personally identifiable information).

**File**: `corpus/text_preprocessor.py`

**Key Features**:
- Unicode normalization (NFC)
- Whitespace standardization
- PII detection and masking:
  - Phone numbers (Sri Lankan formats)
  - Email addresses
  - NIC numbers (old: 123456789V, new: 12-digit)
- Sentence segmentation (language-aware)
- Romanized spelling normalization

**Usage**:
```python
from corpus import TextPreprocessor

preprocessor = TextPreprocessor(remove_pii=True)
result = preprocessor.preprocess("Call me at 0771234567")
# result.cleaned_text = "Call me at [REDACTED]"
# result.pii_detected = [PIIMatch(type=PHONE, ...)]
```

---

### Step 6: Named Entity Recognition

**Goal**: Extract health entities (hospitals, diseases, symptoms).

**File**: `corpus/entity_extractor.py`

**Key Features**:
- Gazette-based matching:
  - 15 Sri Lankan hospitals with aliases
  - 7 diseases (dengue, COVID, TB, etc.)
  - 7 symptoms (fever, headache, cough, etc.)
  - 7 clinic types (OPD, dental, eye, etc.)
- Pattern-based extraction:
  - Times (8:00 AM, morning, etc.)
  - Dates (DD/MM/YYYY, weekdays)
  - Phone numbers

**Usage**:
```python
from corpus import HealthEntityExtractor

extractor = HealthEntityExtractor()
result = extractor.extract("I visited National Hospital for dengue treatment")
# result.entities = [
#   Entity(type=HOSPITAL, text="National Hospital", normalized="National Hospital of Sri Lanka"),
#   Entity(type=DISEASE, text="dengue", normalized="Dengue Fever")
# ]
```

---

### Step 7: Intent Classification

**Goal**: Classify health query intents.

**File**: `corpus/intent_classifier.py`

**Supported Intents**:
- `asking_location` - Where is the clinic?
- `asking_time` - What time does it open?
- `asking_symptoms` - What are the symptoms?
- `asking_treatment` - How to treat?
- `asking_appointment` - How to book?
- `asking_contact` - Phone number?
- `general_info` - Tell me about...
- `emergency` - Urgent help

**Usage**:
```python
from corpus import HealthIntentClassifier

classifier = HealthIntentClassifier()
result = classifier.classify("Where is the dengue clinic?")
# result.intent = Intent.ASKING_LOCATION
# result.confidence = 0.7
```

---

### Step 8: Domain Tagging

**Goal**: Tag content with health domains.

**File**: `corpus/domain_tagger.py`

**Supported Domains**:
- `dengue`, `covid`, `vaccination`
- `mental_health`, `maternal_health`, `child_health`
- `opd`, `emergency`, `pharmacy`, `laboratory`
- `dental`, `eye`, `general`

**Usage**:
```python
from corpus import HealthDomainTagger

tagger = HealthDomainTagger()
result = tagger.tag("Prevention tips for dengue fever and mosquito control")
# result.primary_domain = HealthDomain.DENGUE
# result.keywords_found = ["dengue", "mosquito"]
```

---

### Step 9: Q&A Pair Extraction

**Goal**: Generate question-answer pairs from content.

**File**: `corpus/qa_generator.py`

**Key Features**:
- FAQ pattern extraction (HTML and plain text)
- Entity-based Q&A generation:
  - Hospital → Location/time questions
  - Disease → Symptoms/treatment questions
- Multilingual Q&A creation via translation

**Usage**:
```python
from corpus import QAGenerator

generator = QAGenerator()
pairs = generator.generate_from_content(
    text="National Hospital is located in Colombo. Open 24 hours.",
    entities=[{"type": "hospital", "text": "National Hospital"}]
)
# pairs = [QAPair(question="Where is the National Hospital?", answer="...")]
```

---

### Step 10: Annotation Storage Layer

**Goal**: Orchestrate entire pipeline and save to database.

**File**: `corpus/annotation_processor.py`

**Pipeline Flow**:
1. Language Detection
2. Romanized Classification (if Latin)
3. Text Preprocessing
4. Entity Extraction
5. Intent Classification
6. Domain Tagging
7. Q&A Generation
8. Save to Supabase

**Usage**:
```python
from corpus import AnnotationProcessor

processor = AnnotationProcessor()
result = processor.process(
    text="mage amma dengue clinic eka koheda",
    context_id="doc123",
    source_url="http://example.com"
)

# Save to database
processor.save_to_supabase(result, repo)
```

---

### Step 11: Bias Auditing System

**Goal**: Track corpus representation and detect gaps.

**File**: `corpus/bias_auditor.py`

**Key Features**:
- Distribution tracking:
  - Language distribution
  - Romanized type distribution
  - Domain distribution
  - Region distribution
- Minimum thresholds:
  - Sinhala: 20%, Tamil: 15%, English: 10%
  - Mental health, maternal health: 5% each
- Alerts for underrepresentation
- Source suggestions for filling gaps

**Usage**:
```python
from corpus import BiasAuditor

auditor = BiasAuditor(repo)
report = auditor.calculate_distribution()
print(report.alerts)  # [BiasAlert(type="language", value="tamil", severity="high")]
```

---

### Step 12: Content Deduplication & Versioning

**Goal**: Detect duplicates and track content changes.

**File**: `corpus/deduplicator.py`

**Key Features**:
- SHA-256 content hashing
- Near-duplicate detection (Jaccard similarity)
- Version history tracking
- Change summaries

**Usage**:
```python
from corpus import ContentDeduplicator

dedup = ContentDeduplicator(repo)
is_dup, match = dedup.is_duplicate("Some content text")
if is_dup:
    print(f"Duplicate of {match.original_id}")
```

---

### Step 13: Scheduled Crawling Automation

**Goal**: Automate crawling and annotation every 12 hours.

**File**: `run_scheduled.py`

**Key Features**:
- Async crawl cycles
- Automatic annotation of new content
- Weekly bias audits (Sundays)
- Configurable intervals

**Usage**:
```bash
# Run continuously
python run_scheduled.py --interval 12

# Run once
python run_scheduled.py --once
```

---

### Step 14: Human Review Interface

**Goal**: UI for reviewing and approving Q&A pairs.

**File**: `web/templates/review.html`

**Features**:
- Card-based Q&A display
- Language/domain badges
- Approve/Reject/Edit buttons
- AJAX verification

---

### Step 15: API & Dashboard

**Goal**: Web interface for monitoring and management.

**Files**:
- `web/app.py` - FastAPI application
- `web/templates/dashboard.html` - Main dashboard
- `web/templates/bias_report.html` - Bias visualization

**API Endpoints**:
- `GET /` - Dashboard
- `GET /review` - Q&A review page
- `GET /bias-report` - Bias report
- `GET /api/stats` - Corpus statistics
- `GET /api/qa-pairs` - List Q&A pairs
- `POST /api/qa-pairs/{id}/verify` - Verify Q&A
- `POST /api/annotate` - Annotate text
- `POST /api/queue/add` - Add URL to queue

**Usage**:
```bash
python web/app.py --port 8000
# Open http://localhost:8000
```

---

## Database Schema

### Extended `raw_ingest` Table
| Column | Type | Description |
|--------|------|-------------|
| detected_language | TEXT | sinhala, tamil, english |
| language_confidence | FLOAT | 0.0 to 1.0 |
| is_romanized | BOOLEAN | True if Singlish/Tamilish |
| romanized_type | TEXT | singlish, tamilish, null |
| translated_text | JSONB | {sinhala: "...", tamil: "...", english: "..."} |
| entities | JSONB | Extracted entities array |
| intent | TEXT | Query intent |
| domain | TEXT | Health domain |
| content_hash | TEXT | SHA-256 hash |
| region | TEXT | Geographic region |

### `qa_pairs` Table
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Primary key |
| question_text | TEXT | Question content |
| question_language | TEXT | Question language |
| question_is_romanized | BOOLEAN | Romanized flag |
| answer_text | TEXT | Answer content |
| intent | TEXT | Query intent |
| domain | TEXT | Health domain |
| entities | JSONB | Related entities |
| source_context_id | TEXT | FK to raw_ingest |
| verified | BOOLEAN | Review status |

### `corpus_statistics` Table
| Column | Type | Description |
|--------|------|-------------|
| snapshot_date | DATE | Report date |
| total_documents | INTEGER | Document count |
| total_qa_pairs | INTEGER | Q&A count |
| language_distribution | JSONB | {sinhala: N, tamil: N, ...} |
| domain_distribution | JSONB | {dengue: N, ...} |
| bias_alerts | JSONB | Alert array |

---

## Usage Guide

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm
```

### Database Setup
```sql
-- Run in Supabase SQL Editor
\i migrations/001_corpus_schema.sql
```

### Quick Start
```python
# Annotate a single text
from corpus import AnnotationProcessor

processor = AnnotationProcessor()
result = processor.process(
    text="mage amma dengue clinic eka koheda",
    context_id="test123"
)

print(f"Language: {result.language.language}")
print(f"Romanized: {result.romanized.classification}")
print(f"Intent: {result.intent.intent}")
print(f"Domain: {result.domain.primary_domain}")
print(f"Entities: {[e.text for e in result.entities.entities]}")
```

### Start Services
```bash
# Start web dashboard
python web/app.py --port 8000

# Start scheduler (12-hour cycle)
python run_scheduled.py --interval 12
```

---

## Summary

This implementation covers all requirements from the IT22919700 project proposal:

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Multilingual support (Si, Ta, En) | ✅ | language_detector.py |
| Romanized detection (Singlish/Tamilish) | ✅ | romanized_classifier.py |
| Translation (NLLB-200) | ✅ | translator.py |
| Deep annotation | ✅ | annotation_processor.py |
| Q&A pair generation | ✅ | qa_generator.py |
| Bias auditing | ✅ | bias_auditor.py |
| Content versioning | ✅ | deduplicator.py |
| Continuous updates | ✅ | run_scheduled.py |
| Human review interface | ✅ | web/templates/review.html |
| API & Dashboard | ✅ | web/app.py |

---

*Generated: 2025-12-31*
*Project: IT22919700 - Multilingual Health Corpus*
