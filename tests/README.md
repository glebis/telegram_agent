# Telegram Agent Test Suite

This comprehensive test suite covers the 4 key features of the Telegram Agent project:

## 🔍 Test Coverage

### 1. Summary Generation (LLM Service) - `test_services/test_llm_service.py`

Tests the AI-powered image analysis and summary generation capabilities:

- **Summary Quality**: Validates that generated summaries meet quality standards (word count, formatting, language)
- **Mode-Based Analysis**: Tests different analysis modes (default, artistic, technical) produce appropriate summaries
- **Batch Processing**: Tests concurrent processing of multiple images for summary generation
- **Text Integration**: Tests integration between text extraction (OCR) and summary generation
- **Error Handling**: Tests graceful handling of API failures and malformed responses
- **Consistency**: Validates that summaries are consistent across multiple attempts

**Key Test Cases:**
```python
test_analyze_image_generates_summary()
test_analyze_image_with_artistic_mode()
test_batch_image_analysis_summaries()
test_summary_quality_validation()
test_mode_based_summary_customization()
```

### 2. Image Processing Pipeline - `test_services/test_image_service.py`

Tests the complete image processing workflow from download to storage:

- **Telegram Integration**: Tests downloading images from Telegram Bot API
- **Format Conversion**: Tests handling of different image formats (PNG, JPEG, WEBP)
- **Compression Pipeline**: Tests image compression and optimization
- **Batch Processing**: Tests concurrent processing of multiple images
- **Metadata Extraction**: Tests extraction of EXIF and image metadata
- **Error Handling**: Tests handling of corrupted or invalid image data
- **Memory Efficiency**: Tests processing of large images without memory issues
- **File Organization**: Tests proper file structure and organization

**Key Test Cases:**
```python
test_download_image_from_telegram()
test_image_compression_pipeline()
test_image_format_conversion()
test_batch_image_processing()
test_memory_efficient_processing()
```

### 3. Vector Similarity Search - `test_services/test_similarity_service.py`

Tests the vector database and similarity search functionality:

- **Basic Similarity Search**: Tests finding similar images based on vector embeddings
- **Threshold Filtering**: Tests filtering results by similarity threshold
- **Result Ranking**: Tests that results are properly ranked by similarity score
- **Duplicate Detection**: Tests identification of near-duplicate images
- **Semantic Search**: Tests text-to-image similarity search
- **Cross-Modal Search**: Tests combining visual and textual embeddings
- **Performance**: Tests search performance with large datasets
- **Clustering**: Tests grouping similar images into clusters

**Key Test Cases:**
```python
test_find_similar_images_basic()
test_similarity_threshold_filtering()
test_duplicate_detection()
test_semantic_similarity_search()
test_performance_with_large_dataset()
```

### 4. Database Operations & Integrity - `test_core/test_database.py`

Tests database functionality, integrity, and performance:

- **CRUD Operations**: Tests Create, Read, Update, Delete operations for all models
- **Health Checks**: Tests database connection and health monitoring
- **Statistics**: Tests user, chat, and image count retrieval
- **Concurrent Operations**: Tests multiple simultaneous database operations
- **Transaction Management**: Tests transaction rollback and commit behaviors
- **Data Integrity**: Tests foreign key constraints and data validation
- **Performance**: Tests bulk operations and connection pool management
- **Migration Simulation**: Tests data migration scenarios

**Key Test Cases:**
```python
test_database_initialization()
test_health_check_success()
test_concurrent_database_operations()
test_transaction_rollback()
test_bulk_operations_performance()
```

## 🚀 Running the Tests

### Run All Tests
```bash
python run_tests.py
```

### Run Individual Test Files
```bash
# Summary generation tests
python -m pytest tests/test_services/test_llm_service.py -v

# Image processing tests  
python -m pytest tests/test_services/test_image_service.py -v

# Similarity search tests
python -m pytest tests/test_services/test_similarity_service.py -v

# Database tests
python -m pytest tests/test_core/test_database.py -v
```

### Run with Coverage
```bash
python -m pytest tests/ --cov=src --cov-report=html --cov-report=term-missing
```

## 🔧 Test Configuration

### Environment Setup
Tests use isolated environments with:
- Temporary databases (SQLite in-memory)
- Mock external APIs (OpenAI, Telegram)
- Temporary file storage
- Test-specific configuration

### Mock Services
- **LLM Service**: Mocked to avoid real API calls and costs
- **Telegram Bot**: Mocked to simulate file downloads and messages
- **Vector Database**: Mocked for predictable similarity search results
- **Embedding Service**: Mocked to return consistent test vectors

### Test Data
- **Sample Images**: Generated programmatically (colored squares, various sizes)
- **Sample Users**: Test user profiles with different states
- **Sample Chats**: Group and private chat configurations
- **Sample Embeddings**: Predefined vectors for similarity testing

## 📊 Coverage Goals

Target coverage by component:
- **Summary Generation**: >90% (critical AI functionality)
- **Image Processing**: >85% (core business logic)
- **Similarity Search**: >80% (algorithm implementation)
- **Database Operations**: >95% (data integrity critical)

## 🔍 Testing Best Practices

### Async Testing
All tests use `pytest-asyncio` for proper async/await testing:
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

### Mocking External Services
```python
@patch('src.services.llm_service.litellm')
async def test_with_mocked_api(mock_litellm):
    mock_litellm.acompletion.return_value = mock_response
    # Test logic here
```

### Temporary Resources
```python
@pytest.fixture
def temp_database():
    with tempfile.NamedTemporaryFile() as db_file:
        yield db_file.name
    # Automatic cleanup
```

## 🐛 Debugging Tests

### Enable Debug Logging
```bash
python -m pytest tests/ -v -s --log-cli-level=DEBUG
```

### Run Specific Test
```bash
python -m pytest tests/test_services/test_llm_service.py::TestLLMService::test_analyze_image_generates_summary -v -s
```

### Inspect Test Coverage
```bash
# Generate HTML coverage report
python -m pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

## 📋 Test Maintenance

### Adding New Tests
1. Create test file in appropriate directory (`test_services/`, `test_core/`, etc.)
2. Follow naming convention: `test_*.py`
3. Use descriptive test method names: `test_feature_description()`
4. Add appropriate fixtures and mocks
5. Update this README with new test descriptions

### Test Data Management
- Keep test data minimal and focused
- Use factories/fixtures for reusable test data
- Clean up temporary resources in teardown methods
- Use meaningful test data that reflects real-world scenarios

### Performance Considerations
- Mock external APIs to avoid network delays
- Use in-memory databases for speed
- Limit test data size for fast execution
- Run expensive tests separately if needed