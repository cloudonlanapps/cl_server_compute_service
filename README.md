# Compute

Task and compute job management microservice for the CL Server platform.

**Server Port:** 8002
**Authentication Method:** ES256 JWT (optional)
**Package Manager:** uv
**Database:** SQLite with WAL mode

> **For Developers:** See [INTERNALS.md](INTERNALS.md) for package structure, development workflow, and contribution guidelines.
>
> **For Testing:** See [tests/README.md](tests/README.md) for comprehensive testing guide, test organization, and coverage requirements.

## Overview

Compute provides REST API endpoints for:
- Job lifecycle management (retrieve, delete)
- Worker capability discovery
- Compute task execution via plugin system
- Job storage management

## Quick Start

### Installation

**Individual Package Installation:**

```bash
# Navigate to the compute service directory
cd services/compute

# Install dependencies (uv will create .venv automatically)
uv sync

# Or install with development dependencies
uv sync --all-extras

# Run database migrations (required before first use)
uv run compute-migrate
```

**Workspace Installation (All Packages):**

See root [README.md](../../README.md) for installing all packages using `./install.sh`.

## CLI Commands & Usage

The service provides three CLI commands for database migrations, server, and worker processes.

**Note:** `CL_SERVER_DIR` environment variable is required for database and job storage location.

### Command 1: compute-migrate (Database Migrations)

Runs database migrations to create or upgrade database tables.

```bash
# Basic usage (run before first use or after pulling migration changes)
uv run compute-migrate
```

**Available Options:**
- None - this is a simple utility command

**When to run:**
- **Once** when setting up a new installation
- **After pulling** changes that include new database migrations

The server will refuse to start if migrations haven't been run, showing a clear error message.

### Command 2: compute-server (Server)

Starts the FastAPI server for job management and compute orchestration.

```bash
# Basic usage (development mode with auto-reload)
uv run compute-server --reload

# Production mode
uv run compute-server

# Custom configuration
uv run compute-server --host 0.0.0.0 --port 8003 --no-auth
```

**Available Options:**
- `--host HOST` - Host to bind to (default: `0.0.0.0`)
- `--port, -p PORT` - Port to bind to (default: `8002`)
- `--reload` - Enable uvicorn auto-reload for development
- `--debug` - Enable debug mode
- `--public-key-path PATH` - Path to public key for JWT validation
- `--no-auth` - Disable authentication checks (dev/testing only)

**Example:**
```bash
uv run compute-server --host 0.0.0.0 --port 8002 --reload
```

### Command 3: compute-worker (Worker)

Executes compute tasks by polling the job queue and processing them using registered plugins.

**Important:** The worker requires the compute server to be running on localhost. It will check server connectivity before starting.

```bash
# Basic usage (connects to localhost:8002)
uv run compute-worker

# Custom configuration
uv run compute-worker --worker-id worker-1 --port 8003 --tasks clip_embedding,face_detection --log-level DEBUG

# Multiple workers for scalability
uv run compute-worker --worker-id worker-1 &
uv run compute-worker --worker-id worker-2 &
```

**Available Options:**
- `--worker-id, -w ID` - Unique worker identifier (default: `worker-default`)
- `--port, -p PORT` - Compute server port on localhost (default: `8002`)
- `--tasks, -t TASKS` - Comma-separated task types to process (default: all available)
- `--log-level, -l LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR (default: `INFO`)

**Example:**
```bash
uv run compute-worker --worker-id worker-1 --port 8002 --tasks image_resize,image_conversion
```

**Worker Shutdown:**
- **First Ctrl+C**: Graceful shutdown (completes current job, cleans up)
- **Second Ctrl+C**: Force immediate exit (no cleanup)

## API Endpoints

### Job Management

- `GET /jobs/{job_id}` - Get job status and results
- `DELETE /jobs/{job_id}` - Delete job and associated files

### Worker Capabilities

- `GET /capabilities` - Get available worker capabilities

### Admin Endpoints

- `GET /admin/jobs/storage/size` - Get total storage usage
- `DELETE /admin/jobs/cleanup?days=7` - Cleanup old jobs

### Compute Plugin Endpoints

Dynamically registered endpoints from cl_ml_tools plugins. See [cl_ml_tools documentation](https://github.com/cloudonlanapps/cl_ml_tools) for available plugins.

## Documentation

- **[INTERNALS.md](./INTERNALS.md)** - Developer documentation, architecture, contributing guide
- **[tests/README.md](./tests/README.md)** - Testing guide with fixtures and patterns
- **[Architecture Overview](../../docs/ARCHITECTURE.md)** - System-wide architecture and inter-service communication

## License

MIT License - see [LICENSE](./LICENSE) file for details.
