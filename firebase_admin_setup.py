"""
Firebase Admin SDK Setup Module
Handles Firebase initialization, authentication, and client creation
"""

import os
import json
from pathlib import Path
from typing import Optional
import firebase_admin  # type: ignore
from firebase_admin import credentials, firestore, storage, auth  # type: ignore
from google.cloud.firestore_v1 import Client as FirestoreClient  # type: ignore
from google.cloud.storage import Bucket  # type: ignore
from google.cloud.firestore import SERVER_TIMESTAMP  # type: ignore


class FirebaseConfig:
    """Configuration manager for Firebase services"""
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize Firebase configuration
        
        Args:
            credentials_path: Path to Firebase service account JSON file
                            If None, will check GOOGLE_APPLICATION_CREDENTIALS env var
        """
        self.credentials_path = credentials_path or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        self._app = None
        self._db = None
        self._storage_client = None
        
        if not self.credentials_path:
            raise ValueError(
                "Firebase credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS "
                "environment variable or pass credentials_path"
            )
        
        # Validate credentials file exists
        if not Path(self.credentials_path).exists():
            raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
    
    def initialize(self, storage_bucket: Optional[str] = None) -> firebase_admin.App:
        """
        Initialize Firebase Admin SDK
        
        Args:
            storage_bucket: Name of default storage bucket (e.g., 'crawl4ai-health-lk.appspot.com')
        
        Returns:
            Firebase App instance
        """
        if self._app:
            print("Firebase already initialized")
            return self._app
        
        try:
            cred = credentials.Certificate(self.credentials_path)
            
            if storage_bucket:
                self._app = firebase_admin.initialize_app(cred, {
                    'storageBucket': storage_bucket
                })
            else:
                # Always use env var for bucket
                bucket_name = os.getenv('FIREBASE_STORAGE_BUCKET')
                if not bucket_name:
                    raise RuntimeError('FIREBASE_STORAGE_BUCKET environment variable not set')
                self._app = firebase_admin.initialize_app(cred, {
                    'storageBucket': bucket_name
                })
        
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Firebase: {str(e)}")
    
    def get_firestore_client(self) -> FirestoreClient:
        """
        Get Firestore database client
        
        Returns:
            Firestore client instance
        """
        if not self._app:
            raise RuntimeError("Firebase not initialized. Call initialize() first")
        
        if not self._db:
            self._db = firestore.client()
            print("✓ Firestore client created")
        
        return self._db
    
    def get_storage_bucket(self, bucket_name: Optional[str] = None) -> Bucket:
        """
        Get Cloud Storage bucket
        
        Args:
            bucket_name: Specific bucket name. If None, uses default bucket
        
        Returns:
            Storage Bucket instance
        """
        if not self._app:
            raise RuntimeError("Firebase not initialized. Call initialize() first")
        
        try:
            if bucket_name:
                bucket = storage.bucket(bucket_name)
            else:
                bucket = storage.bucket()
            
            print(f"✓ Storage bucket accessed: {bucket.name}")
            return bucket
        
        except Exception as e:
            raise RuntimeError(f"Failed to access storage bucket: {str(e)}")
    
    def create_user(self, email: str, password: str, role: str = 'annotator') -> dict:
        """
        Create Firebase user with custom role
        
        Args:
            email: User email
            password: User password
            role: User role (annotator, expert, admin, crawler)
        
        Returns:
            User info dictionary
        """
        if not self._app:
            raise RuntimeError("Firebase not initialized. Call initialize() first")
        
        try:
            # Create authentication user
            user = auth.create_user(
                email=email,
                password=password
            )
            
            # Store role in Firestore
            db = self.get_firestore_client()
            db.collection('users').document(user.uid).set({
                'email': email,
                'role': role,
                'created_at': SERVER_TIMESTAMP,
                'active': True
            })
            
            print(f"✓ User created: {email} (role: {role})")
            
            return {
                'uid': user.uid,
                'email': user.email,
                'role': role
            }
        
        except Exception as e:
            raise RuntimeError(f"Failed to create user: {str(e)}")
    
    def set_user_role(self, uid: str, role: str) -> None:
        """
        Update user role in Firestore
        
        Args:
            uid: User UID
            role: New role (annotator, expert, admin, crawler)
        """
        valid_roles = ['annotator', 'expert', 'admin', 'crawler']
        if role not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of: {valid_roles}")
        
        db = self.get_firestore_client()
        db.collection('users').document(uid).update({
            'role': role,
            'updated_at': SERVER_TIMESTAMP
        })
        
        print(f"✓ User {uid} role updated to: {role}")
    
    def initialize_collections(self) -> None:
        """
        Initialize Firestore collections with initial documents
        Creates the required collection structure
        """
        db = self.get_firestore_client()
        
        collections = {
            'raw_ingest': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Raw crawled data storage'
                }
            },
            'curated_corpus': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Curated and validated data'
                }
            },
            'audit_logs': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'System audit logs'
                }
            },
            'crawl_queue': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'URLs queued for crawling'
                }
            },
            'annotations': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Human annotations and corrections'
                }
            },
            'ontology_diseases': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Medical ontology - diseases'
                }
            },
            'ontology_symptoms': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Medical ontology - symptoms'
                }
            },
            'ontology_facilities': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Medical ontology - health facilities'
                }
            },
            'clinic_schedules': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Clinic schedules and availability'
                }
            },
            'bias_metrics': {
                '_init': {
                    'initialized': True,
                    'timestamp': SERVER_TIMESTAMP,
                    'description': 'Corpus bias tracking metrics'
                }
            }
        }
        
        for collection_name, docs in collections.items():
            for doc_id, data in docs.items():
                db.collection(collection_name).document(doc_id).set(data)
        
        print(f"✓ Initialized {len(collections)} collections")
    
    def cleanup(self) -> None:
        """Delete Firebase app instance"""
        if self._app:
            firebase_admin.delete_app(self._app)
            self._app = None
            self._db = None
            self._storage_client = None
            print("✓ Firebase app deleted")


# Singleton instance for easy access
_firebase_instance: Optional[FirebaseConfig] = None


def get_firebase_instance(credentials_path: Optional[str] = None) -> FirebaseConfig:
    """
    Get or create Firebase singleton instance
    
    Args:
        credentials_path: Path to credentials (only used on first call)
    
    Returns:
        FirebaseConfig instance
    """
    global _firebase_instance
    
    if _firebase_instance is None:
        _firebase_instance = FirebaseConfig(credentials_path)
    
    return _firebase_instance


# Convenience functions
def init_firebase(credentials_path: Optional[str] = None, storage_bucket: Optional[str] = None):
    """Initialize Firebase with default configuration"""
    fb = get_firebase_instance(credentials_path)
    if storage_bucket:
        fb.initialize(storage_bucket)
    else:
        fb.initialize()
    return fb


def get_db() -> FirestoreClient:
    """Get Firestore client from singleton"""
    return get_firebase_instance().get_firestore_client()


def get_bucket(bucket_name: Optional[str] = None) -> Bucket:
    """Get Storage bucket from singleton"""
    return get_firebase_instance().get_storage_bucket(bucket_name)


if __name__ == "__main__":
    # Example usage
    print("Firebase Admin Setup Module")
    print("=" * 50)
    print("\nUsage:")
    print("  from firebase_admin_setup import init_firebase, get_db, get_bucket")
    print("\n  # Initialize")
    print("  init_firebase('path/to/credentials.json', 'your-bucket.appspot.com')")
    print("\n  # Use services")
    print("  db = get_db()")
    print("  bucket = get_bucket()")
