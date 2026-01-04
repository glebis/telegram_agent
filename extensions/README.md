# SQLite Extensions

This directory contains pre-compiled SQLite extensions for vector similarity search.

## Included Extensions

- **vss0.dylib** - sqlite-vss extension for vector similarity search
- **vector0.dylib** - vector operations support library

## Platform Compatibility

**These binaries are compiled for macOS (arm64/Apple Silicon).**

### For Linux Users

You'll need to compile the extensions from source:

```bash
# Clone sqlite-vss
git clone https://github.com/asg017/sqlite-vss.git
cd sqlite-vss

# Build (requires cmake and make)
make loadable
```

The compiled `.so` files should be placed in this directory.

### For Windows Users

Compile from source or use WSL with the Linux instructions above.

## Usage

The extensions are loaded by the application at runtime via:
```python
import sqlite3
conn = sqlite3.connect("database.db")
conn.enable_load_extension(True)
conn.load_extension("./extensions/vss0")
conn.load_extension("./extensions/vector0")
```

## Source Repository

- [sqlite-vss](https://github.com/asg017/sqlite-vss) - SQLite extension for vector search
