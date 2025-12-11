"""
Quick Setup Script for Firebase Infrastructure
Run this after creating Firebase project and downloading credentials
"""

import sys
import os
from pathlib import Path


def check_prerequisites():
    """Check if required tools and files are available"""
    print("🔍 Checking prerequisites...\n")
    
    checks = {
        "Python 3.8+": sys.version_info >= (3, 8),
        "Environment variable set": os.getenv('GOOGLE_APPLICATION_CREDENTIALS') is not None,
    }
    
    if checks["Environment variable set"]:
        cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if cred_path:
            checks["Credentials file exists"] = Path(cred_path).exists()
    
    all_passed = True
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")
        if not passed:
            all_passed = False
    
    print()
    return all_passed


def install_dependencies():
    """Install Python dependencies"""
    print("📦 Installing Python dependencies...\n")
    
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✓ Dependencies installed successfully\n")
        return True
    else:
        print(f"✗ Failed to install dependencies:\n{result.stderr}\n")
        return False


def initialize_firebase():
    """Initialize Firebase and create collections"""
    print("🔥 Initializing Firebase...\n")
    
    try:
        from firebase_admin_setup import init_firebase
        
        # Get storage bucket from environment or use default
        storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET', 'crawl4ai-health-lk.appspot.com')
        
        fb = init_firebase(
            credentials_path=os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
            storage_bucket=storage_bucket
        )
        
        print("✓ Firebase initialized\n")
        
        # Initialize collections
        print("📚 Creating collection structure...\n")
        fb.initialize_collections()
        print("✓ Collections created\n")
        
        return True
    
    except Exception as e:
        print(f"✗ Firebase initialization failed: {str(e)}\n")
        return False


def create_admin_user():
    """Create initial admin user"""
    print("👤 Creating admin user...\n")
    
    try:
        from firebase_admin_setup import get_firebase_instance
        
        fb = get_firebase_instance()
        
        print("Enter admin credentials:")
        email = input("  Email: ").strip()
        
        if not email:
            print("✗ Email required\n")
            return False
        
        # Generate secure password or let user input
        import secrets
        import string
        
        use_generated = input("  Generate secure password? (y/n): ").strip().lower() == 'y'
        
        if use_generated:
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
            password = ''.join(secrets.choice(alphabet) for _ in range(16))
            print(f"  Generated password: {password}")
        else:
            password = input("  Password: ").strip()
        
        admin_user = fb.create_user(
            email=email,
            password=password,
            role='admin'
        )
        
        print(f"\n✓ Admin user created successfully!")
        print(f"  UID: {admin_user['uid']}")
        print(f"  Email: {admin_user['email']}")
        print(f"  Role: {admin_user['role']}")
        
        if use_generated:
            print(f"\n⚠️  SAVE THIS PASSWORD: {password}")
        
        print()
        return True
    
    except Exception as e:
        print(f"✗ Failed to create admin user: {str(e)}\n")
        return False


def run_tests():
    """Run test suite"""
    print("🧪 Running tests...\n")
    
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_firebase_setup.py", "-v", "--tb=short"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    
    if result.returncode == 0:
        print("\n✓ All tests passed!\n")
        return True
    else:
        print("\n⚠️  Some tests failed. Check output above.\n")
        return False


def main():
    """Run complete setup process"""
    print("=" * 60)
    print("  Crawl4AI Multi-Agent System - Firebase Setup")
    print("=" * 60)
    print()
    
    # Step 1: Check prerequisites
    if not check_prerequisites():
        print("❌ Prerequisites check failed!")
        print("\nPlease ensure:")
        print("  1. Python 3.8+ is installed")
        print("  2. GOOGLE_APPLICATION_CREDENTIALS environment variable is set")
        print("  3. Service account key file exists")
        print("\nExample:")
        print("  $env:GOOGLE_APPLICATION_CREDENTIALS='C:\\path\\to\\serviceAccountKey.json'")
        return 1
    
    # Step 2: Install dependencies
    print("Step 1/5: Installing dependencies")
    if not install_dependencies():
        print("❌ Failed to install dependencies")
        return 1
    
    # Step 3: Initialize Firebase
    print("Step 2/5: Initializing Firebase")
    if not initialize_firebase():
        print("❌ Firebase initialization failed")
        return 1
    
    # Step 4: Create admin user
    print("Step 3/5: Creating admin user")
    create_admin = input("Create admin user now? (y/n): ").strip().lower()
    if create_admin == 'y':
        create_admin_user()
    else:
        print("⚠️  Skipping admin user creation\n")
    
    # Step 5: Run tests
    print("Step 4/5: Running tests")
    run_tests_now = input("Run test suite? (y/n): ").strip().lower()
    if run_tests_now == 'y':
        run_tests()
    else:
        print("⚠️  Skipping tests\n")
    
    # Summary
    print("=" * 60)
    print("  ✅ Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Deploy security rules: firebase deploy --only firestore,storage")
    print("  2. Deploy Cloud Functions: firebase deploy --only functions")
    print("  3. Run tests: pytest test_firebase_setup.py -v")
    print("  4. Proceed to Step 2: Crawl4AI Integration")
    print()
    print("Documentation: See README.md for detailed instructions")
    print()
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        sys.exit(1)
