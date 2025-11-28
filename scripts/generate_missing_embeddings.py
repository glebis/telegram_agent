#!/usr/bin/env python3
"""
Migration script to generate embeddings for existing images in the database.

This script will:
1. Find all images without embeddings that have accessible files
2. Generate embeddings using the EmbeddingService
3. Store embeddings in both the main database and vector database
4. Provide progress reporting and error handling

Usage:
    python scripts/generate_missing_embeddings.py --help
    python scripts/generate_missing_embeddings.py --all
    python scripts/generate_missing_embeddings.py --user-id 123456789
    python scripts/generate_missing_embeddings.py --batch-size 5 --dry-run
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

import typer
from dotenv import load_dotenv
from sqlalchemy import select, func

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import get_db_session, init_database
from src.models.image import Image
from src.models.chat import Chat
from src.services.embedding_service import get_embedding_service
from src.core.vector_db import get_vector_db

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = typer.Typer(help="Generate embeddings for existing images in the database")


async def get_images_without_embeddings(user_id: Optional[int] = None) -> List[Image]:
    """Get all images without embeddings that have accessible files"""
    
    async with get_db_session() as session:
        # Base query for images without embeddings
        query = select(Image).where(
            Image.embedding.is_(None),
            Image.processing_status == "completed"
        )
        
        # Filter by user if specified
        if user_id:
            query = query.join(Image.chat).where(Chat.user_id == user_id)
        
        # Order by creation date (oldest first)
        query = query.order_by(Image.created_at)
        
        result = await session.execute(query)
        images = result.scalars().all()
        
        # Filter for images with accessible files
        accessible_images = []
        for image in images:
            file_path = None
            
            # Check compressed_path first, then original_path
            if hasattr(image, 'compressed_path') and image.compressed_path:
                file_path = Path(image.compressed_path)
            elif hasattr(image, 'original_path') and image.original_path:
                file_path = Path(image.original_path)
            elif hasattr(image, 'file_path') and image.file_path:
                file_path = Path(image.file_path)
            
            if file_path and file_path.exists():
                accessible_images.append(image)
                logger.debug(f"Found accessible image: {image.id} at {file_path}")
            else:
                logger.warning(f"Image {image.id} has no accessible file path")
        
        return accessible_images


async def get_embedding_statistics(user_id: Optional[int] = None) -> dict:
    """Get statistics about embeddings in the database"""
    
    async with get_db_session() as session:
        # Base queries
        base_query = select(Image).where(Image.processing_status == "completed")
        
        if user_id:
            base_query = base_query.join(Image.chat).where(Chat.user_id == user_id)
        
        # Total completed images
        total_result = await session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total_images = total_result.scalar() or 0
        
        # Images with embeddings
        with_embeddings_query = base_query.where(Image.embedding.isnot(None))
        with_embeddings_result = await session.execute(
            select(func.count()).select_from(with_embeddings_query.subquery())
        )
        with_embeddings = with_embeddings_result.scalar() or 0
        
        # Images without embeddings
        without_embeddings = total_images - with_embeddings
        
        # Coverage percentage
        coverage = (with_embeddings / total_images * 100) if total_images > 0 else 0
        
        return {
            "total_images": total_images,
            "with_embeddings": with_embeddings,
            "without_embeddings": without_embeddings,
            "coverage_percentage": coverage,
            "user_id": user_id
        }


async def process_images_batch(
    images: List[Image], 
    embedding_service, 
    vector_db,
    dry_run: bool = False
) -> dict:
    """Process a batch of images to generate embeddings"""
    
    results = {
        "processed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": []
    }
    
    for image in images:
        try:
            logger.info(f"Processing image {image.id} (file_id: {image.file_id})")
            
            # Find accessible file path
            file_path = None
            if hasattr(image, 'compressed_path') and image.compressed_path:
                file_path = Path(image.compressed_path)
            elif hasattr(image, 'original_path') and image.original_path:
                file_path = Path(image.original_path)
            elif hasattr(image, 'file_path') and image.file_path:
                file_path = Path(image.file_path)
            
            if not file_path or not file_path.exists():
                logger.warning(f"No accessible file for image {image.id}")
                results["skipped"] += 1
                continue
            
            if dry_run:
                logger.info(f"DRY RUN: Would process {file_path}")
                results["processed"] += 1
                continue
            
            # Read image data
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            # Generate embedding
            embedding_bytes = await embedding_service.generate_embedding(image_data)
            
            if not embedding_bytes:
                logger.error(f"Failed to generate embedding for image {image.id}")
                results["failed"] += 1
                results["errors"].append(f"Image {image.id}: Embedding generation failed")
                continue
            
            # Update database record
            async with get_db_session() as session:
                # Refresh the image object in this session
                await session.refresh(image)
                
                # Update with embedding
                image.embedding = embedding_bytes
                image.embedding_model = embedding_service.model_name
                
                await session.commit()
                
                # Store in vector database
                success = await vector_db.store_embedding(image.id, embedding_bytes)
                if not success:
                    logger.warning(f"Failed to store embedding in vector database for image {image.id}")
            
            logger.info(f"Successfully generated embedding for image {image.id}")
            results["processed"] += 1
            
        except Exception as e:
            logger.error(f"Error processing image {image.id}: {e}")
            results["failed"] += 1
            results["errors"].append(f"Image {image.id}: {str(e)}")
    
    return results


@app.command()
def generate(
    user_id: Optional[int] = typer.Option(None, help="Process images for specific user ID only"),
    batch_size: int = typer.Option(10, help="Number of images to process in each batch"),
    dry_run: bool = typer.Option(False, help="Show what would be processed without making changes"),
    all_users: bool = typer.Option(False, help="Process images for all users"),
    env_file: str = typer.Option(".env.local", help="Environment file to load")
):
    """Generate embeddings for existing images without embeddings"""

    # Load environment (same order as main app)
    # 1. ~/.env (global user API keys)
    # 2. project .env (project defaults)
    # 3. project .env.local (local overrides)
    home_env = Path.home() / ".env"
    project_env = project_root / ".env"
    env_path = Path(env_file)

    if home_env.exists():
        load_dotenv(home_env, override=False)
        typer.echo(f"📁 Loaded global environment from {home_env}")

    if project_env.exists():
        load_dotenv(project_env, override=True)
        typer.echo(f"📁 Loaded environment from {project_env}")

    if env_path.exists():
        load_dotenv(env_path, override=True)
        typer.echo(f"✅ Loaded environment from {env_file}")
    elif not home_env.exists() and not project_env.exists():
        typer.echo(f"⚠️  Warning: No .env files found, using system environment")
    
    # Validate parameters
    if not all_users and not user_id:
        typer.echo("❌ Please specify either --user-id <ID> or --all-users")
        raise typer.Exit(1)
    
    if all_users and user_id:
        typer.echo("❌ Cannot specify both --user-id and --all-users")
        raise typer.Exit(1)
    
    async def main():
        try:
            # Initialize database
            await init_database()
            typer.echo("✅ Database initialized")
            
            # Get services
            embedding_service = get_embedding_service()
            vector_db = get_vector_db()
            
            # Get statistics
            stats = await get_embedding_statistics(user_id if not all_users else None)
            
            typer.echo(f"\n📊 Embedding Statistics:")
            if user_id:
                typer.echo(f"   User ID: {user_id}")
            elif all_users:
                typer.echo(f"   Scope: All users")
            typer.echo(f"   Total completed images: {stats['total_images']}")
            typer.echo(f"   Images with embeddings: {stats['with_embeddings']}")
            typer.echo(f"   Images without embeddings: {stats['without_embeddings']}")
            typer.echo(f"   Coverage: {stats['coverage_percentage']:.1f}%")
            
            if stats['without_embeddings'] == 0:
                typer.echo("✅ All images already have embeddings!")
                return
            
            # Get images without embeddings
            typer.echo(f"\n🔍 Finding images without embeddings...")
            images_to_process = await get_images_without_embeddings(user_id if not all_users else None)
            
            typer.echo(f"📋 Found {len(images_to_process)} images with accessible files to process")
            
            if len(images_to_process) == 0:
                typer.echo("✅ No images need processing!")
                return
            
            if dry_run:
                typer.echo(f"\n🧪 DRY RUN MODE - No changes will be made")
            
            # Process in batches
            total_results = {
                "processed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": []
            }
            
            for i in range(0, len(images_to_process), batch_size):
                batch = images_to_process[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(images_to_process) + batch_size - 1) // batch_size
                
                typer.echo(f"\n🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} images)...")
                
                batch_results = await process_images_batch(
                    batch, embedding_service, vector_db, dry_run
                )
                
                # Aggregate results
                for key in ['processed', 'failed', 'skipped']:
                    total_results[key] += batch_results[key]
                total_results['errors'].extend(batch_results['errors'])
                
                typer.echo(f"   ✅ Processed: {batch_results['processed']}")
                typer.echo(f"   ❌ Failed: {batch_results['failed']}")
                typer.echo(f"   ⏭️  Skipped: {batch_results['skipped']}")
            
            # Final summary
            typer.echo(f"\n📈 Final Results:")
            typer.echo(f"   ✅ Successfully processed: {total_results['processed']}")
            typer.echo(f"   ❌ Failed: {total_results['failed']}")
            typer.echo(f"   ⏭️  Skipped: {total_results['skipped']}")
            
            if total_results['errors']:
                typer.echo(f"\n❌ Errors encountered:")
                for error in total_results['errors'][:10]:  # Show first 10 errors
                    typer.echo(f"   • {error}")
                if len(total_results['errors']) > 10:
                    typer.echo(f"   ... and {len(total_results['errors']) - 10} more errors")
            
            if not dry_run and total_results['processed'] > 0:
                # Get updated statistics
                updated_stats = await get_embedding_statistics(user_id if not all_users else None)
                typer.echo(f"\n📊 Updated Coverage: {updated_stats['coverage_percentage']:.1f}%")
                typer.echo("✅ Embedding generation completed!")
            
        except Exception as e:
            typer.echo(f"❌ Error: {e}")
            raise typer.Exit(1)
    
    # Run the async main function
    asyncio.run(main())


@app.command()
def stats(
    user_id: Optional[int] = typer.Option(None, help="Get stats for specific user ID only"),
    env_file: str = typer.Option(".env.local", help="Environment file to load")
):
    """Show embedding statistics for the database"""
    
    # Load environment
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
    
    async def main():
        try:
            await init_database()
            
            stats = await get_embedding_statistics(user_id)
            
            typer.echo(f"📊 Embedding Statistics")
            typer.echo("=" * 40)
            if user_id:
                typer.echo(f"User ID: {user_id}")
            else:
                typer.echo("Scope: All users")
            typer.echo(f"Total completed images: {stats['total_images']}")
            typer.echo(f"Images with embeddings: {stats['with_embeddings']}")
            typer.echo(f"Images without embeddings: {stats['without_embeddings']}")
            typer.echo(f"Coverage: {stats['coverage_percentage']:.1f}%")
            
            # Show recommendation
            if stats['without_embeddings'] > 0:
                typer.echo(f"\n💡 Recommendation:")
                typer.echo(f"   Run: python scripts/generate_missing_embeddings.py generate --all-users")
                typer.echo(f"   This will enable similarity search for all {stats['without_embeddings']} images")
            else:
                typer.echo(f"\n✅ All images have embeddings - similarity search is fully enabled!")
                
        except Exception as e:
            typer.echo(f"❌ Error: {e}")
            raise typer.Exit(1)
    
    asyncio.run(main())


if __name__ == "__main__":
    app()