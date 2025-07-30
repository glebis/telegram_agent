# Embedding Migration Guide

This guide explains how to generate embeddings for existing images in the database to enable similarity search functionality.

## Overview

The Telegram Agent uses CLIP embeddings to enable similar image search in artistic mode. By default, embeddings are only generated for new images uploaded in artistic mode. This migration allows you to retroactively generate embeddings for all existing images, regardless of their original processing mode.

## Prerequisites

- Telegram Agent development environment set up
- Database with existing processed images
- CLIP model dependencies installed (`sentence-transformers`, `torch`)
- Sufficient disk space and processing time for embedding generation

## Migration Script

The main migration script is located at `scripts/generate_missing_embeddings.py`.

### Quick Start

```bash
# Check current embedding coverage
python scripts/generate_missing_embeddings.py stats

# Generate embeddings for all users (dry run first)
python scripts/generate_missing_embeddings.py generate --all-users --dry-run

# Actually generate embeddings for all users
python scripts/generate_missing_embeddings.py generate --all-users

# Generate embeddings for specific user only
python scripts/generate_missing_embeddings.py generate --user-id 123456789
```

### Command Options

#### `stats` command
Show embedding statistics for the database:

```bash
python scripts/generate_missing_embeddings.py stats [OPTIONS]

Options:
  --user-id INTEGER    Get stats for specific user ID only
  --env-file TEXT      Environment file to load [default: .env.local]
```

#### `generate` command
Generate embeddings for existing images:

```bash
python scripts/generate_missing_embeddings.py generate [OPTIONS]

Options:
  --user-id INTEGER      Process images for specific user ID only
  --batch-size INTEGER   Number of images to process in each batch [default: 10]
  --dry-run             Show what would be processed without making changes
  --all-users           Process images for all users
  --env-file TEXT       Environment file to load [default: .env.local]
```

## How It Works

### 1. Image Selection
The script identifies images that need embedding generation by:
- Finding images without embeddings (`embedding IS NULL`)
- Ensuring images have completed processing (`processing_status = 'completed'`)
- Checking that image files are accessible on disk
- Filtering by user if specified

### 2. File Path Resolution
The script looks for image files in this order of preference:
1. `compressed_path` - Processed/compressed image
2. `original_path` - Original uploaded image
3. `file_path` - Alternative file path

### 3. Embedding Generation
- Uses CLIP ViT-B-32 model for 512-dimensional embeddings
- Processes images in configurable batches (default: 10)
- Stores embeddings in both main database and vector database
- Provides progress reporting and error handling

### 4. Database Updates
For each successfully processed image:
- Updates `embedding` field with binary embedding data
- Sets `embedding_model` to track which model was used
- Stores embedding in vector database for efficient similarity search

## Expected Results

### Before Migration
```
📊 Embedding Statistics
========================================
Scope: All users
Total completed images: 15
Images with embeddings: 2
Images without embeddings: 13
Coverage: 13.3%
```

### After Migration
```
📊 Embedding Statistics
========================================
Scope: All users
Total completed images: 15
Images with embeddings: 15
Images without embeddings: 0
Coverage: 100.0%
```

## Performance Considerations

### Processing Time
- **CLIP model loading**: ~5-10 seconds (one-time)
- **Per image embedding**: ~0.5-2 seconds
- **Batch of 10 images**: ~5-20 seconds

### Resource Usage
- **CPU**: High during embedding generation
- **Memory**: ~2-4GB for CLIP model
- **Disk**: Minimal additional storage (~2KB per embedding)

### Recommendations
- Run during low-usage periods
- Use appropriate batch sizes (5-20 depending on system)
- Monitor system resources during processing

## Error Handling

The script handles various error conditions gracefully:

### File Access Errors
- Missing image files are skipped with warnings
- Inaccessible file paths are logged but don't stop processing
- Corrupted images are skipped with error logging

### Model Errors
- CLIP model loading failures are reported
- Individual embedding generation failures are logged
- Processing continues with remaining images

### Database Errors
- Database connection issues are handled
- Failed database updates are logged
- Vector database storage errors don't affect main process

## Integration with Bot

Once embeddings are generated:

1. **Similarity Search Enabled**: All images can now be found through similarity search
2. **Artistic Mode Enhancement**: Users will see actual similar images instead of "No similar images found"
3. **Cross-Mode Compatibility**: Images originally processed in default mode can now match with artistic mode images

## Monitoring and Validation

### Health Endpoint
The `/health` endpoint now includes embedding statistics:

```json
{
  "status": "healthy",
  "service": "telegram-agent",
  "database": "connected",
  "stats": {
    "users": 5,
    "chats": 8,
    "images": 15
  },
  "embedding_stats": {
    "total_images": 15,
    "with_embeddings": 15,
    "without_embeddings": 0,
    "coverage_percentage": 100.0
  }
}
```

### Programmatic Access
Use the `SimilarityService.get_user_similarity_stats()` method for per-user statistics.

## Troubleshooting

### Common Issues

**"No images found that need embedding regeneration"**
- All images already have embeddings
- Check that images exist with `processing_status = 'completed'`
- Verify image files are accessible on disk

**"Failed to generate embedding for image X"**
- Image file may be corrupted
- Check available memory (CLIP model needs ~2GB)
- Verify image format is supported (JPG, PNG, WebP)

**"Vector database initialization failed"**
- sqlite-vss extension may not be available
- Script continues with fallback similarity search
- Vector search will be less efficient but still functional

### Recovery Options

If migration fails partway through:
1. **Resume**: Run the script again - it will skip images that already have embeddings
2. **User-specific**: Process specific users with `--user-id` option
3. **Smaller batches**: Reduce `--batch-size` for systems with limited resources

## Best Practices

1. **Test First**: Always run with `--dry-run` to preview changes
2. **Check Stats**: Use `stats` command to understand scope before migration
3. **Incremental Processing**: Process users individually for large databases
4. **Monitor Resources**: Watch CPU and memory usage during processing
5. **Backup Database**: Create database backup before large migrations

## Future Maintenance

### New Images
New images uploaded in artistic mode will automatically get embeddings - no manual intervention needed.

### Model Updates
If switching to a different embedding model:
1. Update `EMBEDDING_MODEL` environment variable
2. Regenerate all embeddings to ensure consistency
3. Use `--all-users` option to process all existing images

### Performance Optimization
For large databases (1000+ images):
- Consider running during off-peak hours
- Use smaller batch sizes to reduce memory pressure
- Monitor vector database performance and rebuild indexes if needed