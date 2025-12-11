"""
Firebase Cloud Functions
Serverless agent endpoints for the multi-agent system
"""

import firebase_admin
from firebase_admin import credentials, firestore, storage
from firebase_functions import https_fn, options
from google.cloud.firestore import SERVER_TIMESTAMP
import json
from datetime import datetime


# Initialize Firebase Admin
if not firebase_admin._apps:
    firebase_admin.initialize_app()


@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["get", "post"],
    )
)
def health_check(req: https_fn.Request) -> https_fn.Response:
    """
    Health check endpoint for Firebase Functions
    """
    return https_fn.Response(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "crawl4ai-multi-agent"
        }),
        status=200,
        headers={"Content-Type": "application/json"}
    )


@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["post"],
    )
)
def initialize_database(req: https_fn.Request) -> https_fn.Response:
    """
    Initialize Firestore collections with default structure
    Admin-only function for first-time setup
    """
    try:
        # Verify admin token (in production, implement proper auth)
        auth_header = req.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return https_fn.Response(
                json.dumps({"error": "Unauthorized"}),
                status=401,
                headers={"Content-Type": "application/json"}
            )
        
        db = firestore.client()
        
        # Initialize collections
        collections = {
            'raw_ingest': 'Raw crawled data storage',
            'curated_corpus': 'Curated and validated data',
            'audit_logs': 'System audit logs',
            'crawl_queue': 'URLs queued for crawling',
            'annotations': 'Human annotations and corrections',
            'ontology_diseases': 'Medical ontology - diseases',
            'ontology_symptoms': 'Medical ontology - symptoms',
            'ontology_facilities': 'Medical ontology - health facilities',
            'clinic_schedules': 'Clinic schedules and availability',
            'bias_metrics': 'Corpus bias tracking metrics'
        }
        
        for collection_name, description in collections.items():
            db.collection(collection_name).document('_init').set({
                'initialized': True,
                'timestamp': SERVER_TIMESTAMP,
                'description': description
            })
        
        return https_fn.Response(
            json.dumps({
                "status": "success",
                "collections_initialized": len(collections),
                "collections": list(collections.keys())
            }),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    
    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )


@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["get"],
    )
)
def get_collection_stats(req: https_fn.Request) -> https_fn.Response:
    """
    Get statistics about Firestore collections
    Returns document counts and metadata
    """
    try:
        db = firestore.client()
        
        collections = [
            'raw_ingest',
            'curated_corpus',
            'audit_logs',
            'crawl_queue',
            'annotations'
        ]
        
        stats = {}
        for collection_name in collections:
            docs = db.collection(collection_name).stream()
            count = sum(1 for _ in docs)
            stats[collection_name] = {
                'document_count': count
            }
        
        return https_fn.Response(
            json.dumps({
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "stats": stats
            }),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    
    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )


@https_fn.on_call()
def create_user_with_role(req: https_fn.CallableRequest) -> dict:
    """
    Cloud Function to create user with custom role
    Callable from client SDKs with authentication
    """
    # Verify caller is admin
    if not req.auth:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="User must be authenticated"
        )
    
    # Check if caller is admin (implement role check)
    db = firestore.client()
    caller_doc = db.collection('users').document(req.auth.uid).get()
    
    caller_data = caller_doc.to_dict() if caller_doc.exists else None
    if not caller_doc.exists or (caller_data and caller_data.get('role') != 'admin'):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Only admins can create users"
        )
    
    # Get parameters
    email = req.data.get('email')
    role = req.data.get('role', 'annotator')
    
    if not email:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Email is required"
        )
    
    valid_roles = ['annotator', 'expert', 'admin', 'crawler']
    if role not in valid_roles:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message=f"Invalid role. Must be one of: {valid_roles}"
        )
    
    try:
        # Create user in Firebase Auth
        from firebase_admin import auth  # type: ignore
        user = auth.create_user(email=email)
        
        # Store role in Firestore
        db.collection('users').document(user.uid).set({
            'email': email,
            'role': role,
            'created_at': SERVER_TIMESTAMP,
            'created_by': req.auth.uid,
            'active': True
        })
        
        return {
            'uid': user.uid,
            'email': user.email,
            'role': role,
            'message': 'User created successfully'
        }
    
    except Exception as e:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=f"Failed to create user: {str(e)}"
        )


@https_fn.on_document_created(document="raw_ingest/{docId}")
def on_raw_ingest_created(event: https_fn.CloudEvent) -> None:
    """
    Firestore trigger: Log when new documents are added to raw_ingest
    """
    doc_id = event.params['docId']
    
    # Log to audit_logs
    db = firestore.client()
    db.collection('audit_logs').add({
        'event_type': 'raw_ingest_created',
        'document_id': doc_id,
        'timestamp': SERVER_TIMESTAMP,
        'data': event.data
    })


@https_fn.on_document_updated(document="annotations/{docId}")
def on_annotation_updated(event: https_fn.CloudEvent) -> None:
    """
    Firestore trigger: Track annotation updates for consensus mechanism
    """
    doc_id = event.params['docId']
    
    db = firestore.client()
    db.collection('audit_logs').add({
        'event_type': 'annotation_updated',
        'document_id': doc_id,
        'timestamp': SERVER_TIMESTAMP,
        'before': event.data.get('before'),
        'after': event.data.get('after')
    })
