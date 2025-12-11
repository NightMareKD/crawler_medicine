# Firebase Setup Instructions

## Option 1: Real Firebase (Cloud)

### Step 1: Create Firebase Project
1. Go to https://console.firebase.google.com/
2. Click "Add Project"
3. Enter project name: `crawl4ai-health-lk`
4. Follow the setup wizard

### Step 2: Get Service Account Key
1. In Firebase Console, go to **Project Settings** (gear icon)
2. Click **Service Accounts** tab
3. Click **"Generate New Private Key"**
4. Save the JSON file as `serviceAccountKey.json` in project root

### Step 3: Enable Services
1. **Firestore Database:**
   - Click "Firestore Database" in left menu
   - Click "Create Database"
   - Choose "Production mode" or "Test mode"
   - Select region closest to Sri Lanka (e.g., `asia-south1`)

2. **Storage:**
   - Click "Storage" in left menu
   - Click "Get Started"
   - Choose security rules (can use test mode initially)

3. **Authentication:**
   - Click "Authentication" in left menu
   - Click "Get Started"
   - Enable "Email/Password" provider

### Step 4: Configure Environment
Create `.env` file:
```bash
GOOGLE_APPLICATION_CREDENTIALS=serviceAccountKey.json
FIREBASE_STORAGE_BUCKET=crawl4ai-health-lk.appspot.com
APP_ENV=production
LOG_LEVEL=INFO
```

### Step 5: Initialize Database
```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Run setup
python setup_firebase.py
```

---

## Option 2: Firebase Emulator (Local Testing)

**No API keys needed! Test locally without cloud costs.**

### Step 1: Install Firebase CLI
```powershell
npm install -g firebase-tools
```

### Step 2: Login (optional for emulator)
```powershell
firebase login
```

### Step 3: Initialize Firebase
```powershell
firebase init
```
Select:
- Firestore
- Storage
- Emulators

### Step 4: Start Emulators
```powershell
firebase emulators:start
```

This starts:
- Firestore: http://localhost:8080
- Storage: http://localhost:9199
- Auth: http://localhost:9099
- UI: http://localhost:4000

### Step 5: Run Tests with Emulator
```powershell
# In test_ingestion_layer.py, set:
USE_EMULATOR = True

# Run tests
python test_ingestion_layer.py
```

---

## Quick Test (Emulator)

```powershell
# Terminal 1: Start emulator
firebase emulators:start

# Terminal 2: Run tests
.\.venv\Scripts\Activate.ps1
python test_ingestion_layer.py
```

---

## Verify Setup

```powershell
# Test Firebase connection
python test_firebase_setup.py

# Test ingestion layer
python test_ingestion_layer.py
```

---

## Troubleshooting

### Error: "Firebase credentials not found"
- Check `.env` file exists
- Verify `GOOGLE_APPLICATION_CREDENTIALS` path is correct
- Or use emulator mode (no credentials needed)

### Error: "Permission denied"
- Check Firestore security rules
- Ensure service account has proper permissions
- Or use emulator with test mode rules

### Error: "Module not found"
- Ensure venv is activated
- Run: `pip install -r requirements.txt`
