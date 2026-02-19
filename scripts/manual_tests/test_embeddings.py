#!/usr/bin/env python3
"""
Test script to verify embedding generation is working properly.

This script will:
1. Test if sentence-transformers is installed
2. Try to load the embedding service
3. Generate a test embedding from a dummy image
4. Report on embedding functionality

Usage:
    python scripts/test_embeddings.py
"""

import asyncio
import logging
import sys
from pathlib import Path
from io import BytesIO

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_image() -> bytes:
    """Create a simple test image"""
    try:
        from PIL import Image, ImageDraw
        
        # Create a simple 100x100 red square
        img = Image.new('RGB', (100, 100), color='red')
        draw = ImageDraw.Draw(img)
        draw.rectangle([25, 25, 75, 75], fill='blue')
        
        # Convert to bytes
        buffer = BytesIO()
        img.save(buffer, format='JPEG')
        return buffer.getvalue()
        
    except ImportError:
        logger.error("PIL (Pillow) not installed - cannot create test image")
        return b"fake_image_data"


async def test_embedding_service():
    """Test the embedding service functionality"""
    
    print("🧪 Testing Embedding Service")
    print("=" * 50)
    
    # Test 1: Check imports
    print("1. Testing imports...")
    try:
        import torch
        print(f"   ✅ PyTorch: {torch.__version__}")
    except ImportError:
        print("   ❌ PyTorch not installed")
        return False
    
    try:
        import sentence_transformers
        print(f"   ✅ SentenceTransformers: {sentence_transformers.__version__}")
    except ImportError:
        print("   ❌ SentenceTransformers not installed")
        print("   💡 Install with: pip install sentence-transformers")
        return False
    
    # Test 2: Import embedding service
    print("\n2. Testing embedding service import...")
    try:
        from src.services.embedding_service import get_embedding_service
        embedding_service = get_embedding_service()
        print(f"   ✅ EmbeddingService imported successfully")
        print(f"   📋 Model: {embedding_service.model_name}")
        print(f"   💾 Device: {embedding_service.device}")
        print(f"   📏 Expected dimension: {embedding_service.embedding_dim}")
    except Exception as e:
        print(f"   ❌ Failed to import embedding service: {e}")
        return False
    
    # Test 3: Generate test embedding
    print("\n3. Testing embedding generation...")
    try:
        test_image_data = create_test_image()
        print(f"   📸 Created test image: {len(test_image_data)} bytes")
        
        embedding_bytes = await embedding_service.generate_embedding(test_image_data)
        
        if embedding_bytes:
            print(f"   ✅ Generated embedding: {len(embedding_bytes)} bytes")
            
            # Test embedding conversion back to array
            embedding_array = embedding_service.bytes_to_array(embedding_bytes)
            if embedding_array is not None:
                print(f"   ✅ Converted back to array: {embedding_array.shape}")
                print(f"   📏 Actual dimension: {len(embedding_array)}")
                
                # Test similarity calculation
                embedding_bytes_2 = await embedding_service.generate_embedding(test_image_data)
                if embedding_bytes_2:
                    similarity = embedding_service.calculate_cosine_similarity(
                        embedding_bytes, embedding_bytes_2
                    )
                    print(f"   ✅ Similarity with self: {similarity:.4f}")
            else:
                print(f"   ❌ Failed to convert embedding back to array")
                return False
        else:
            print(f"   ❌ Failed to generate embedding")
            return False
            
    except Exception as e:
        print(f"   ❌ Error during embedding generation: {e}")
        logger.error(f"Embedding generation error details: {e}", exc_info=True)
        return False
    
    # Test 4: Model information
    print("\n4. Model information...")
    try:
        model_info = embedding_service.get_model_info()
        for key, value in model_info.items():
            print(f"   📋 {key}: {value}")
    except Exception as e:
        print(f"   ⚠️  Could not get model info: {e}")
    
    print("\n✅ All embedding tests passed!")
    print("\n💡 Next steps:")
    print("   • Try uploading an image in artistic mode")
    print("   • Check that embeddings are generated and stored")
    print("   • Verify similarity search works")
    
    return True


async def test_vector_database():
    """Test vector database functionality"""
    
    print("\n\n🗄️  Testing Vector Database")
    print("=" * 50)
    
    try:
        from src.core.vector_db import get_vector_db
        vector_db = get_vector_db()
        
        print("1. Testing vector database initialization...")
        success = await vector_db.initialize_vector_support()
        
        if success:
            print("   ✅ Vector database initialized successfully")
            print("   📋 sqlite-vss extension loaded")
        else:
            print("   ⚠️  Vector database initialization failed")
            print("   📋 Will use fallback similarity search")
        
        return success
        
    except Exception as e:
        print(f"   ❌ Error testing vector database: {e}")
        return False


if __name__ == "__main__":
    async def main():
        success = await test_embedding_service()
        await test_vector_database()
        
        if success:
            print("\n🎉 Embedding system is ready!")
        else:
            print("\n❌ Embedding system needs attention")
            sys.exit(1)
    
    asyncio.run(main())