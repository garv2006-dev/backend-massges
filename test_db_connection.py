"""
Test script to verify PostgreSQL connection with async configuration.
Run this after setting up your .env file with DATABASE_URL.
"""
import asyncio
from app.database import engine, init_db
from app.config import settings

async def test_connection():
    """Test database connection."""
    print(f"Testing connection to: {settings.DATABASE_URL}")
    
    try:
        # Test connection
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            print("✓ Database connection successful!")
            
        # Initialize database tables
        print("Initializing database tables...")
        await init_db()
        print("✓ Database tables initialized!")
        
    except Exception as e:
        print(f"✗ Connection failed: {str(e)}")
        print("\nPlease ensure:")
        print("1. PostgreSQL is running")
        print("2. DATABASE_URL in .env is correct")
        print("3. Database exists")

if __name__ == "__main__":
    asyncio.run(test_connection())
