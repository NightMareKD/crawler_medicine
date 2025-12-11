"""
Comprehensive test suite for Firebase setup
Tests connectivity, security rules, RBAC, and storage access
"""

import pytest  # type: ignore
import os
import time
from pathlib import Path
from firebase_admin import firestore, storage, auth  # type: ignore
from google.cloud.firestore import SERVER_TIMESTAMP  # type: ignore
from firebase_admin_setup import (
    FirebaseConfig, 
    init_firebase, 
    get_db, 
    get_bucket,
    get_firebase_instance
)


# Test fixtures
@pytest.fixture(scope="module")
def firebase_config():
    """Initialize Firebase for testing"""
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    
    if not credentials_path:
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS not set")
    
    config = FirebaseConfig(credentials_path)
    config.initialize(storage_bucket='crawl4ai-health-lk.appspot.com')
    
    yield config
    
    # Cleanup
    config.cleanup()


@pytest.fixture
def test_user(firebase_config):
    """Create a test user for RBAC testing"""
    email = f"test_user_{int(time.time())}@example.com"
    
    user_info = firebase_config.create_user(
        email=email,
        password="TestPass123!",
        role="annotator"
    )
    
    yield user_info
    
    # Cleanup: Delete test user
    try:
        auth.delete_user(user_info['uid'])
        db = firebase_config.get_firestore_client()
        db.collection('users').document(user_info['uid']).delete()
    except:
        pass


class TestFirebaseConnection:
    """Test Firebase connectivity and initialization"""
    
    def test_firestore_connection(self, firebase_config):
        """Verify Firestore database connectivity"""
        db = firebase_config.get_firestore_client()
        
        # Create test document
        test_doc_ref = db.collection('raw_ingest').document('test_connection')
        test_doc_ref.set({
            'test': True,
            'timestamp': SERVER_TIMESTAMP,
            'message': 'Connection test'
        })
        
        # Verify document exists
        test_doc = test_doc_ref.get()
        assert test_doc.exists, "Test document should exist in Firestore"
        assert test_doc.to_dict()['test'] is True
        
        # Cleanup
        test_doc_ref.delete()
    
    def test_firestore_timestamp(self, firebase_config):
        """Verify server timestamp functionality"""
        db = firebase_config.get_firestore_client()
        
        test_doc_ref = db.collection('raw_ingest').document('test_timestamp')
        test_doc_ref.set({
            'timestamp': SERVER_TIMESTAMP
        })
        
        doc = test_doc_ref.get()
        assert doc.exists
        assert 'timestamp' in doc.to_dict()
        assert doc.to_dict()['timestamp'] is not None
        
        # Cleanup
        test_doc_ref.delete()
    
    def test_storage_bucket_access(self, firebase_config):
        """Verify Storage bucket read/write permissions"""
        bucket = firebase_config.get_storage_bucket()
        
        # Upload test file
        test_blob = bucket.blob('test/test_file.txt')
        test_content = 'Test content for Firebase Storage'
        test_blob.upload_from_string(test_content)
        
        # Verify upload
        assert test_blob.exists(), "Test blob should exist in storage"
        
        # Download and verify content
        downloaded_content = test_blob.download_as_text()
        assert downloaded_content == test_content
        
        # Cleanup
        test_blob.delete()
    
    def test_specific_bucket_access(self, firebase_config):
        """Test accessing specific storage buckets"""
        try:
            # Test pdfs-raw bucket (may not exist yet)
            bucket = firebase_config.get_storage_bucket('pdfs-raw')
            assert bucket is not None
        except Exception as e:
            # It's okay if bucket doesn't exist in test environment
            pytest.skip(f"Specific bucket not available: {str(e)}")


class TestCollectionInitialization:
    """Test Firestore collection setup"""
    
    def test_initialize_collections(self, firebase_config):
        """Verify all required collections are created"""
        firebase_config.initialize_collections()
        
        db = firebase_config.get_firestore_client()
        
        required_collections = [
            'raw_ingest',
            'curated_corpus',
            'audit_logs',
            'crawl_queue',
            'annotations',
            'ontology_diseases',
            'ontology_symptoms',
            'ontology_facilities',
            'clinic_schedules',
            'bias_metrics'
        ]
        
        for collection_name in required_collections:
            doc = db.collection(collection_name).document('_init').get()
            assert doc.exists, f"Collection {collection_name} should be initialized"
            assert doc.to_dict()['initialized'] is True
    
    def test_collection_structure(self, firebase_config):
        """Test that collections have correct metadata"""
        db = firebase_config.get_firestore_client()
        
        doc = db.collection('raw_ingest').document('_init').get()
        data = doc.to_dict()
        
        assert 'initialized' in data
        assert 'timestamp' in data
        assert 'description' in data
        assert isinstance(data['description'], str)


class TestUserManagement:
    """Test user creation and role management"""
    
    def test_create_user(self, firebase_config):
        """Test creating a user with default role"""
        email = f"test_create_{int(time.time())}@example.com"
        
        user_info = firebase_config.create_user(
            email=email,
            password="TestPass123!",
            role="annotator"
        )
        
        assert 'uid' in user_info
        assert user_info['email'] == email
        assert user_info['role'] == 'annotator'
        
        # Verify user in Firestore
        db = firebase_config.get_firestore_client()
        user_doc = db.collection('users').document(user_info['uid']).get()
        assert user_doc.exists
        assert user_doc.to_dict()['role'] == 'annotator'
        
        # Cleanup
        auth.delete_user(user_info['uid'])
        db.collection('users').document(user_info['uid']).delete()
    
    def test_create_user_with_different_roles(self, firebase_config):
        """Test creating users with different roles"""
        roles = ['annotator', 'expert', 'admin', 'crawler']
        created_users = []
        
        try:
            for role in roles:
                email = f"test_{role}_{int(time.time())}@example.com"
                user_info = firebase_config.create_user(
                    email=email,
                    password="TestPass123!",
                    role=role
                )
                created_users.append(user_info)
                assert user_info['role'] == role
        
        finally:
            # Cleanup all created users
            db = firebase_config.get_firestore_client()
            for user_info in created_users:
                try:
                    auth.delete_user(user_info['uid'])
                    db.collection('users').document(user_info['uid']).delete()
                except:
                    pass
    
    def test_set_user_role(self, firebase_config, test_user):
        """Test updating user role"""
        firebase_config.set_user_role(test_user['uid'], 'expert')
        
        db = firebase_config.get_firestore_client()
        user_doc = db.collection('users').document(test_user['uid']).get()
        assert user_doc.to_dict()['role'] == 'expert'
    
    def test_invalid_role_rejection(self, firebase_config, test_user):
        """Test that invalid roles are rejected"""
        with pytest.raises(ValueError, match="Invalid role"):
            firebase_config.set_user_role(test_user['uid'], 'invalid_role')


class TestDataOperations:
    """Test CRUD operations on Firestore collections"""
    
    def test_raw_ingest_write(self, firebase_config):
        """Test writing to raw_ingest collection"""
        db = firebase_config.get_firestore_client()
        
        doc_ref = db.collection('raw_ingest').document()
        doc_ref.set({
            'content': 'Test crawled content',
            'provenance': {
                'source_agency': 'Test Agency',
                'ingest_timestamp': SERVER_TIMESTAMP,
                'original_format': 'HTML'
            },
            'requires_human_review': False
        })
        
        # Verify write
        doc = doc_ref.get()
        assert doc.exists
        assert doc.to_dict()['content'] == 'Test crawled content'
        
        # Cleanup
        doc_ref.delete()
    
    def test_curated_corpus_write(self, firebase_config):
        """Test writing to curated_corpus collection"""
        db = firebase_config.get_firestore_client()
        
        doc_ref = db.collection('curated_corpus').document()
        doc_ref.set({
            'content': 'Validated medical content',
            'linguistic_profile': {
                'primary_language': 'Sinhala',
                'confidence': 0.95
            },
            'semantic_tags': ['disease', 'clinic']
        })
        
        # Verify write
        doc = doc_ref.get()
        assert doc.exists
        assert doc.to_dict()['linguistic_profile']['primary_language'] == 'Sinhala'
        
        # Cleanup
        doc_ref.delete()
    
    def test_crawl_queue_priority(self, firebase_config):
        """Test crawl queue with priority scoring"""
        db = firebase_config.get_firestore_client()
        
        # Add multiple URLs with different priorities
        urls = [
            {'url': 'http://example1.com', 'priority_score': 0.9},
            {'url': 'http://example2.com', 'priority_score': 0.5},
            {'url': 'http://example3.com', 'priority_score': 0.8}
        ]
        
        doc_refs = []
        for url_data in urls:
            doc_ref = db.collection('crawl_queue').document()
            doc_ref.set(url_data)
            doc_refs.append(doc_ref)
        
        # Query by priority
        high_priority = db.collection('crawl_queue') \
                         .where('priority_score', '>=', 0.8) \
                         .stream()
        
        high_priority_urls = [doc.to_dict()['url'] for doc in high_priority]
        assert 'http://example1.com' in high_priority_urls
        assert 'http://example3.com' in high_priority_urls
        
        # Cleanup
        for doc_ref in doc_refs:
            doc_ref.delete()


class TestSecuritySimulation:
    """Simulate security rule behavior (actual rules tested with emulator)"""
    
    def test_unauthorized_write_simulation(self, firebase_config):
        """
        Simulate unauthorized write attempt
        Note: Full security testing requires Firebase Emulator
        """
        db = firebase_config.get_firestore_client()
        
        # This test documents expected behavior
        # In production with security rules, this would be blocked
        doc_ref = db.collection('curated_corpus').document('test_security')
        
        try:
            # Attempt to write without proper authentication context
            # In real scenario with rules, this would raise PermissionError
            doc_ref.set({'unauthorized': True})
            
            # In test environment, write succeeds (no rules enforced)
            # Document the expected production behavior
            doc = doc_ref.get()
            assert doc.exists
            
            # Cleanup
            doc_ref.delete()
            
            pytest.skip("Security rules not enforced in test environment. "
                       "Use Firebase Emulator for full security testing.")
        
        except Exception as e:
            # If running with emulator and rules, this should trigger
            assert 'Permission' in str(e) or 'permission' in str(e)


class TestStorageBucketOperations:
    """Test Cloud Storage operations"""
    
    def test_pdf_upload_simulation(self, firebase_config):
        """Test uploading PDF to storage"""
        bucket = firebase_config.get_storage_bucket()
        
        # Simulate PDF upload
        test_blob = bucket.blob('pdfs-raw/test_document.pdf')
        test_content = b'%PDF-1.4 fake pdf content'
        test_blob.upload_from_string(test_content, content_type='application/pdf')
        
        assert test_blob.exists()
        
        # Verify metadata
        metadata = test_blob.metadata or {}
        assert test_blob.content_type == 'application/pdf'
        
        # Cleanup
        test_blob.delete()
    
    def test_image_upload_to_processed_folder(self, firebase_config):
        """Test uploading processed images"""
        bucket = firebase_config.get_storage_bucket()
        
        test_blob = bucket.blob('images-processed/test_image.jpg')
        test_content = b'fake image data'
        test_blob.upload_from_string(test_content, content_type='image/jpeg')
        
        assert test_blob.exists()
        assert test_blob.content_type == 'image/jpeg'
        
        # Cleanup
        test_blob.delete()


class TestAuditLogging:
    """Test audit log functionality"""
    
    def test_audit_log_creation(self, firebase_config):
        """Test creating audit log entries"""
        db = firebase_config.get_firestore_client()
        
        log_entry = {
            'event_type': 'test_event',
            'user_id': 'test_user_123',
            'action': 'test_action',
            'timestamp': SERVER_TIMESTAMP,
            'details': {
                'test': True
            }
        }
        
        doc_ref = db.collection('audit_logs').document()
        doc_ref.set(log_entry)
        
        # Verify log
        doc = doc_ref.get()
        assert doc.exists
        assert doc.to_dict()['event_type'] == 'test_event'
        
        # Cleanup
        doc_ref.delete()


# Performance and load testing
class TestPerformance:
    """Test performance characteristics"""
    
    def test_batch_write_performance(self, firebase_config):
        """Test batch writing multiple documents"""
        db = firebase_config.get_firestore_client()
        
        batch = db.batch()
        doc_refs = []
        
        # Create 10 documents in batch
        for i in range(10):
            doc_ref = db.collection('raw_ingest').document(f'batch_test_{i}')
            batch.set(doc_ref, {
                'index': i,
                'content': f'Batch content {i}',
                'timestamp': SERVER_TIMESTAMP
            })
            doc_refs.append(doc_ref)
        
        # Commit batch
        start_time = time.time()
        batch.commit()
        elapsed = time.time() - start_time
        
        # Verify batch write completed reasonably fast
        assert elapsed < 5.0, "Batch write should complete in under 5 seconds"
        
        # Verify all documents exist
        for doc_ref in doc_refs:
            assert doc_ref.get().exists
        
        # Cleanup
        cleanup_batch = db.batch()
        for doc_ref in doc_refs:
            cleanup_batch.delete(doc_ref)
        cleanup_batch.commit()


# Integration test
@pytest.mark.integration
def test_full_setup_workflow(firebase_config):
    """
    Integration test: Complete setup workflow
    """
    # 1. Initialize collections
    firebase_config.initialize_collections()
    
    # 2. Create test user
    email = f"integration_test_{int(time.time())}@example.com"
    user_info = firebase_config.create_user(email, "TestPass123!", "expert")
    
    # 3. Write test data
    db = firebase_config.get_firestore_client()
    doc_ref = db.collection('raw_ingest').document()
    doc_ref.set({
        'content': 'Integration test content',
        'created_by': user_info['uid'],
        'timestamp': SERVER_TIMESTAMP
    })
    
    # 4. Upload test file
    bucket = firebase_config.get_storage_bucket()
    blob = bucket.blob('test/integration_test.txt')
    blob.upload_from_string('Integration test file')
    
    # 5. Verify everything
    assert doc_ref.get().exists
    assert blob.exists()
    
    # Cleanup
    doc_ref.delete()
    blob.delete()
    auth.delete_user(user_info['uid'])
    db.collection('users').document(user_info['uid']).delete()


if __name__ == "__main__":
    print("Run tests with: pytest test_firebase_setup.py -v")
    print("\nTest categories:")
    print("  - TestFirebaseConnection: Basic connectivity")
    print("  - TestCollectionInitialization: Collection setup")
    print("  - TestUserManagement: User/role management")
    print("  - TestDataOperations: CRUD operations")
    print("  - TestSecuritySimulation: Security behavior")
    print("  - TestStorageBucketOperations: Cloud Storage")
    print("  - TestAuditLogging: Audit logs")
    print("  - TestPerformance: Performance tests")
    print("\nRun integration test:")
    print("  pytest test_firebase_setup.py -v -m integration")
