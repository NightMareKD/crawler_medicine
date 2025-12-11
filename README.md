# Step 1: Firebase Project Setup & Security Infrastructure

Complete Firebase backend setup for the Crawl4AI Multi-Agent Health Information System for Sri Lanka.

## 📋 Overview

This implementation establishes the foundational Firebase infrastructure including:
- Firestore database with 10 collections
- Cloud Storage with 3 buckets (pdfs-raw, images-processed, backups)
- Role-Based Access Control (RBAC) for 4 user types
- Firebase Cloud Functions for serverless agents
- Comprehensive security rules
- Complete test suite

## 🏗️ Architecture

### Firestore Collections

| Collection | Purpose | Access Control |
|------------|---------|----------------|
| `raw_ingest` | Raw crawled data storage | Crawlers write, All authenticated read |
| `curated_corpus` | Validated data with embeddings | Experts/Admins write, All read |
| `audit_logs` | System activity tracking | Admin only |
| `crawl_queue` | URL priority queue | Crawlers/Admins write, All read |
| `annotations` | Human corrections | Annotators create, Experts approve |
| `ontology_diseases` | Medical disease entities | All read, Admins write |
| `ontology_symptoms` | Medical symptom entities | All read, Admins write |
| `ontology_facilities` | Health facility data | All read, Admins write |
| `clinic_schedules` | Public clinic schedules | Public read, Admins write |
| `bias_metrics` | Corpus demographic tracking | Admin only |

### User Roles (RBAC)

1. **Annotator**: Create annotations, tag entities, correct OCR errors
2. **Expert**: Approve annotations, curate corpus, validate medical data
3. **Admin**: Full access, user management, system configuration
4. **Crawler**: Automated agent write access to raw_ingest and crawl_queue

### Storage Buckets

- **pdfs-raw**: Original PDF documents from government sources
- **images-processed**: OCR-processed images
- **backups**: Automated database backups

## 🚀 Quick Start

### Prerequisites

```powershell
# Install Firebase CLI
npm install -g firebase-tools

# Install Python dependencies
pip install firebase-admin pytest
```

### 1. Create Firebase Project

```powershell
# Login to Firebase
firebase login

# Create new project (via Firebase Console)
# Visit: https://console.firebase.google.com/
# Project name: crawl4ai-health-lk
```

### 2. Download Service Account Credentials

1. Go to Firebase Console → Project Settings → Service Accounts
2. Click "Generate New Private Key"
3. Save as `serviceAccountKey.json`
4. Set environment variable:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\serviceAccountKey.json"
```

### 3. Initialize Firebase Project

```powershell
# In project directory
firebase init

# Select:
# - Firestore
# - Storage
# - Functions (Python)
# - Hosting (optional)

# Use existing project: crawl4ai-health-lk
```

### 4. Deploy Security Rules

```powershell
# Deploy Firestore rules and indexes
firebase deploy --only firestore

# Deploy Storage rules
firebase deploy --only storage
```

### 5. Initialize Collections

```python
# Initialize database structure
from firebase_admin_setup import init_firebase

# Initialize with your credentials
fb = init_firebase(
    credentials_path='serviceAccountKey.json',
    storage_bucket='crawl4ai-health-lk.appspot.com'
)

# Create collection structure
fb.initialize_collections()
print("✓ Collections initialized")
```

### 6. Create Admin User

```python
from firebase_admin_setup import get_firebase_instance

fb = get_firebase_instance()

# Create admin user
admin_user = fb.create_user(
    email='admin@crawl4ai.lk',
    password='SecurePass123!',
    role='admin'
)
print(f"Admin created: {admin_user['email']}")
```

### 7. Deploy Cloud Functions

```powershell
# Deploy serverless functions
firebase deploy --only functions
```

## 🧪 Testing

### Run Test Suite

```powershell
# Set credentials environment variable
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\serviceAccountKey.json"

# Run all tests
pytest test_firebase_setup.py -v

# Run specific test class
pytest test_firebase_setup.py::TestFirebaseConnection -v

# Run integration tests
pytest test_firebase_setup.py -v -m integration
```

### Test Categories

```powershell
# Connection tests
pytest test_firebase_setup.py::TestFirebaseConnection -v

# User management tests
pytest test_firebase_setup.py::TestUserManagement -v

# Security simulation
pytest test_firebase_setup.py::TestSecuritySimulation -v

# Performance tests
pytest test_firebase_setup.py::TestPerformance -v
```

### Testing with Firebase Emulator

```powershell
# Install emulators
firebase init emulators

# Start emulators (Firestore on port 8080, Storage on 9199)
firebase emulators:start

# Run tests against emulator
$env:FIRESTORE_EMULATOR_HOST="localhost:8080"
$env:FIREBASE_STORAGE_EMULATOR_HOST="localhost:9199"
pytest test_firebase_setup.py -v
```

## 📝 Usage Examples

### Basic Operations

```python
from firebase_admin_setup import init_firebase, get_db, get_bucket

# Initialize
fb = init_firebase('serviceAccountKey.json', 'crawl4ai-health-lk.appspot.com')

# Get Firestore client
db = get_db()

# Write to raw_ingest
doc_ref = db.collection('raw_ingest').document()
doc_ref.set({
    'content': 'Dengue cases rising in Colombo',
    'provenance': {
        'source_agency': 'Epidemiology Unit',
        'original_format': 'PDF',
        'reliability_score': 0.95
    },
    'timestamp': firestore.SERVER_TIMESTAMP
})

# Upload PDF to storage
bucket = get_bucket()
blob = bucket.blob('pdfs-raw/epid_report_2025.pdf')
blob.upload_from_filename('local_file.pdf')

print(f"Document ID: {doc_ref.id}")
print(f"Storage URL: {blob.public_url}")
```

### User Management

```python
from firebase_admin_setup import get_firebase_instance

fb = get_firebase_instance()

# Create annotator
annotator = fb.create_user(
    email='annotator1@crawl4ai.lk',
    password='AnnotatorPass123!',
    role='annotator'
)

# Create expert
expert = fb.create_user(
    email='expert1@crawl4ai.lk',
    password='ExpertPass123!',
    role='expert'
)

# Update role
fb.set_user_role(annotator['uid'], 'expert')
```

### Query Examples

```python
from firebase_admin_setup import get_db

db = get_db()

# Query documents needing review
docs_needing_review = db.collection('raw_ingest') \
    .where('requires_human_review', '==', True) \
    .where('review_status', '==', 'pending') \
    .order_by('provenance.ingest_timestamp', direction='DESCENDING') \
    .limit(10) \
    .stream()

for doc in docs_needing_review:
    print(f"{doc.id}: {doc.to_dict()['content'][:50]}...")

# Query high-priority crawl queue items
high_priority_urls = db.collection('crawl_queue') \
    .where('priority_score', '>=', 0.8) \
    .order_by('priority_score', direction='DESCENDING') \
    .stream()

for url_doc in high_priority_urls:
    data = url_doc.to_dict()
    print(f"Priority {data['priority_score']}: {data['url']}")
```

## 🔒 Security Configuration

### Firestore Security Rules Highlights

```javascript
// Example: Raw ingest - crawlers write, authenticated read
match /raw_ingest/{document} {
  allow read: if request.auth != null;
  allow write: if hasRole('admin') || hasRole('crawler');
  allow update: if hasRole('annotator') || hasRole('expert') || hasRole('admin');
}

// Public clinic schedules
match /clinic_schedules/{document} {
  allow read: if true;  // Public read
  allow write: if hasRole('admin') || hasRole('expert');
}
```

### Storage Security Rules Highlights

```javascript
// PDFs bucket - crawlers upload, authenticated read
match /pdfs-raw/{allPaths=**} {
  allow read: if request.auth != null;
  allow write: if hasRole('admin') || hasRole('crawler');
}

// Backups - admin only
match /backups/{allPaths=**} {
  allow read: if hasRole('admin');
  allow write: if hasRole('admin');
}
```

## 🔧 Cloud Functions API

### Endpoints

#### 1. Health Check
```powershell
# GET https://your-region-your-project.cloudfunctions.net/health_check
curl https://us-central1-crawl4ai-health-lk.cloudfunctions.net/health_check
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-27T10:30:00Z",
  "service": "crawl4ai-multi-agent"
}
```

#### 2. Initialize Database
```powershell
# POST with admin token
curl -X POST `
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" `
  https://us-central1-crawl4ai-health-lk.cloudfunctions.net/initialize_database
```

#### 3. Get Collection Stats
```powershell
# GET collection document counts
curl https://us-central1-crawl4ai-health-lk.cloudfunctions.net/get_collection_stats
```

## 📊 Monitoring & Maintenance

### View Logs

```powershell
# Stream function logs
firebase functions:log

# Firestore audit logs
# Via Firebase Console → Firestore → audit_logs collection
```

### Backup Strategy

```powershell
# Manual backup export
gcloud firestore export gs://crawl4ai-health-lk-backups/$(Get-Date -Format "yyyy-MM-dd")

# Automated backup (schedule with Cloud Scheduler)
# Set up in Firebase Console → Cloud Scheduler
```

### Monitor Usage

```powershell
# Check Firestore usage
firebase firestore:databases:list

# Check Storage usage
gsutil du -sh gs://crawl4ai-health-lk.appspot.com
```

## 💰 Cost Optimization

### Firebase Spark Plan (Free Tier)

- **Firestore**: 50K reads/day, 20K writes/day, 1GB storage
- **Storage**: 5GB storage, 1GB downloads/day
- **Functions**: 125K invocations/month, 40K GB-seconds

### Estimated Monthly Cost (Beyond Free Tier)

Assuming:
- 10K documents/day ingestion
- 50K API calls/day
- 20GB storage

**Estimated**: ~5,000 LKR (~$15 USD)/month on Blaze Plan

### Cost Reduction Tips

1. Use batch writes (500 writes = 1 batch operation)
2. Implement client-side caching
3. Use Cloud Storage for large files, Firestore for metadata
4. Set up usage alerts in Firebase Console

## 🐛 Troubleshooting

### Common Issues

#### 1. Credentials Not Found

```powershell
# Error: GOOGLE_APPLICATION_CREDENTIALS not set
# Solution:
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\serviceAccountKey.json"
```

#### 2. Permission Denied Errors

```python
# Error: Permission denied on Firestore write
# Solution: Check user role in users collection
db.collection('users').document('USER_UID').get().to_dict()['role']
```

#### 3. Storage Bucket Not Found

```python
# Error: Bucket not found
# Solution: Verify bucket name matches Firebase config
firebase.storage().bucket('crawl4ai-health-lk.appspot.com')
```

#### 4. Import Errors in Tests

```powershell
# Error: Import "firebase_admin" could not be resolved
# Solution: Install dependencies
pip install firebase-admin pytest
```

## 📚 Next Steps

After completing Step 1, proceed to:

1. **Step 2**: Crawl4AI Integration & Adaptive Crawler Agent
2. **Step 3**: OCR Engine with Tesseract
3. **Step 4**: PII Scrubbing Firewall
4. **Step 5**: Linguistic Normalizer Agent

## 🤝 Contributing

### Adding New Collections

1. Update `firestore.rules` with security rules
2. Add indexes to `firestore.indexes.json` if needed
3. Update `initialize_collections()` in `firebase_admin_setup.py`
4. Write tests in `test_firebase_setup.py`
5. Deploy: `firebase deploy --only firestore`

### Testing Checklist

- [ ] All tests pass: `pytest test_firebase_setup.py -v`
- [ ] Security rules deployed: `firebase deploy --only firestore`
- [ ] Functions deployed: `firebase deploy --only functions`
- [ ] Collections initialized
- [ ] Admin user created
- [ ] Backups configured

## 📞 Support

For issues or questions:
- GitHub Issues: [your-repo/issues]
- Email: support@crawl4ai.lk
- Documentation: [full-docs-link]

---

## ✅ Verification Checklist

Run through this checklist to verify setup:

```powershell
# 1. Test Firebase connection
pytest test_firebase_setup.py::TestFirebaseConnection::test_firestore_connection -v

# 2. Test user creation
pytest test_firebase_setup.py::TestUserManagement::test_create_user -v

# 3. Test storage access
pytest test_firebase_setup.py::TestFirebaseConnection::test_storage_bucket_access -v

# 4. Test collections initialized
pytest test_firebase_setup.py::TestCollectionInitialization::test_initialize_collections -v

# 5. Check Cloud Functions
curl https://your-region-your-project.cloudfunctions.net/health_check

# 6. Verify security rules deployed
firebase firestore:rules get
```

**Status Legend:**
- ✓ Complete
- ⚠ Needs attention
- ✗ Not working

---

**Implementation Complete**: Step 1 - Firebase Project Setup & Security Infrastructure

Total time estimate: 2-3 hours for full setup and testing.
