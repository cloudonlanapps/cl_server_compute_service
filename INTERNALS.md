# Compute - Developer Documentation

## Overview

Compute is a FastAPI microservice that manages compute jobs and worker capabilities. It integrates with the cl_ml_tools plugin system and uses shared infrastructure from cl_server_shared.

## Package Structure

```
compute/
├── src/compute/
│   ├── __init__.py           # Public API exports
│   ├── compute_server.py     # Server CLI entry point
│   ├── compute_worker.py     # Worker CLI entry point
│   ├── task_server.py        # FastAPI app
│   ├── routes.py             # API routes
│   ├── service.py            # Business logic
│   ├── schemas.py            # Pydantic models
│   ├── models.py             # Database models (re-exports)
│   ├── database.py           # Database configuration and migrations
│   ├── auth.py               # Authentication
│   ├── capability_manager.py # Worker capability tracking
│   ├── plugins.py            # Plugin system integration
│   ├── utils.py              # Utility functions (directory/server checks)
│   └── worker.py             # Worker implementation
├── tests/                    # Test suite
├── alembic/                  # Database migrations
│   └── versions/             # Migration scripts
├── pyproject.toml            # Package configuration
├── README.md                 # User documentation
└── INTERNALS.md              # This file
```

## Development Setup

### Prerequisites

- Python 3.12+
- uv package manager
- Running MQTT broker (for worker capabilities)
- CL Server shared packages (cl_ml_tools, cl_server_shared)

### Installation

```bash
# Install all dependencies including dev tools
uv sync --all-extras
```

### Running Tests

See [tests/README.md](tests/README.md) for detailed testing information.

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test file
uv run pytest tests/test_routes.py -v
```

### Code Quality

```bash
# Format code
uv run ruff format src/

# Lint code
uv run ruff check src/

# Type checking (if configured)
uv run basedpyright
```

## Architecture

### Service Components

1. **Routes** (`routes.py`) - FastAPI endpoint definitions
2. **Services** (`service.py`) - Business logic layer
   - `JobService` - Job management operations
   - `CapabilityService` - Worker capability queries
3. **Capability Manager** (`capability_manager.py`) - MQTT-based worker discovery
4. **Plugins** (`plugins.py`) - Integration with cl_ml_tools plugin system
5. **Database** (`database.py`) - SQLAlchemy session management with WAL mode and migrations
6. **Utils** (`utils.py`) - Utility functions for startup validation
   - `ensure_cl_server_dir()` - Creates CL_SERVER_DIR (server only)
   - `validate_cl_server_dir_exists()` - Validates CL_SERVER_DIR exists (worker only)
   - `check_server_running()` - Checks if server is accessible on a port
   - `ensure_server_running()` - Validates server is running or exits (worker only)

### Database

- Uses shared models from `cl_server_shared` (Job, QueueEntry)
- Connects to WORKER_DATABASE_URL (shared with worker service)
- SQLite with WAL mode for concurrent access
- Alembic for migrations (run via `compute-migrate` CLI)

**Migration Strategy:**
- Migrations are run separately using `uv run compute-migrate`
- Server validates tables exist on startup (fails with clear error if not)
- Worker does NOT run migrations - relies on user to run `compute-migrate` first
- This keeps server startup fast and predictable

### Authentication

- JWT-based authentication using ES256 keys
- Shared public key from auth service
- Permission-based access control:
  - `ai_inference_support` - Required for job operations
  - `admin` - Required for admin endpoints

### Startup and Initialization

**Database Migration** (`compute-migrate` CLI):
1. Must be run BEFORE starting server (only needed once or after schema changes)
2. Creates CL_SERVER_DIR if needed
3. Runs Alembic migrations (`alembic upgrade head`)
4. Creates all required database tables

**Server Startup** (`compute_server.py`):
1. Parse command-line arguments
2. **Create CL_SERVER_DIR** - `ensure_cl_server_dir()` creates directory if needed
3. Set environment variables (AUTH_DISABLED, etc.)
4. Import and start FastAPI application
5. **Check database tables exist** - Validates migrations have been run
6. Start uvicorn server (fails if tables don't exist)

**Worker Startup** (`compute_worker.py`):
1. Parse command-line arguments (includes `--port` for server port)
2. **Check server is running** - `ensure_server_running()` verifies server on `localhost:PORT`
3. **Validate CL_SERVER_DIR exists** - `validate_cl_server_dir_exists()` ensures server created it
4. Import ComputeWorker class
5. Start worker main loop

**Separation of Responsibilities:**
- **Server owns**: Directory creation, database migrations, table creation
- **Worker owns**: Reading/writing database records, processing jobs
- **Worker requires**: Server must be running before worker can start

### Worker Capability Discovery

- Uses cl_ml_tools broadcaster (MQTT)
- Subscribes to worker capability topics
- Caches worker capabilities and idle counts
- Provides aggregated capability information

### Worker Execution (`worker.py`)

The worker is a standalone process that executes compute jobs:

**Prerequisites:**
- Compute server must be running on localhost
- CL_SERVER_DIR must exist (created by server)
- Database tables must exist (created by server migrations)

1. **Plugin Discovery**
   - Auto-discovers plugins from `pyproject.toml` entry points
   - Uses `cl_ml_tools.worker.get_task_registry()`
   - Filters tasks based on `--tasks` CLI argument or Config

2. **Job Processing**
   - Polls job repository for available jobs
   - Uses `cl_ml_tools.Worker.run_once()` for atomic job claiming
   - Executes tasks in-process using registered plugins
   - Updates job status and progress via repository

3. **Capability Broadcasting**
   - Publishes worker capabilities to MQTT periodically
   - Includes list of supported tasks and idle state
   - Sets MQTT Last Will & Testament (LWT) for clean disconnection
   - Heartbeat interval: `Config.MQTT_HEARTBEAT_INTERVAL`

4. **Graceful Shutdown**
   - Handles SIGINT/SIGTERM signals (Ctrl+C)
   - **First signal**: Initiates graceful shutdown
     - Completes current job before exiting
     - Clears retained MQTT capability messages
     - Closes broadcaster connection cleanly
   - **Second signal**: Forces immediate exit
     - Terminates worker immediately without cleanup
     - Use when graceful shutdown is taking too long

## Plugin System

Task Server integrates with cl_ml_tools plugin system.

**Note:** Uses cl_ml_tools plugins. When adding a new plugin, update plugin registration in pyproject.toml under `[project.entry-points."cl_ml_tools.tasks"]`. The plugin system is provided by cl_ml_tools package - see its documentation for available plugins and how to create custom plugins.

**Integration Points:**
1. **Plugin Registration** - Plugins register via pyproject.toml entry points
2. **API Routes** - `create_master_router()` creates plugin routes mounted on FastAPI app
3. **Worker Discovery** - Worker auto-discovers all registered plugins using `get_task_registry()`

**Note:** For system-wide architecture and inter-service communication, see [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) in the repository root.

## Development Workflow

### Adding New Endpoints

1. Add route function to `routes.py`
2. Add service method to `service.py`
3. Add response schema to `schemas.py`
4. Write tests in `tests/`

### Database Migrations

**Migration Command:**

Users must run migrations BEFORE starting the server:

```bash
uv run compute-migrate
```

This creates all required database tables. Only run when:
- Setting up a new installation
- After pulling changes with new migrations

**Creating New Migrations (for developers):**

```bash
# Create versions directory if needed
mkdir -p alembic/versions

# Create a new migration after schema changes
uv run alembic revision --autogenerate -m "description"

# Users will run compute-migrate to apply the new migration
```

**Manual Alembic Commands (for development/debugging):**

```bash
# Check current migration version
uv run alembic current

# View migration history
uv run alembic history

# Rollback one migration (development only)
uv run alembic downgrade -1
```

**Note:**
- Server validates tables exist on startup - fails if migrations haven't been run
- `compute-migrate` is a separate CLI tool (not part of server startup)
- The `alembic/versions` directory must exist and contain at least one migration file

## Configuration

All configuration is managed through `cl_server_shared.Config` class:
- Environment variables loaded at startup
- Shared across all CL Server services
- See cl_server_shared documentation for full config options

## Testing Strategy

See [tests/README.md](tests/README.md) for comprehensive testing documentation, including test organization, fixtures, and coverage requirements.

Tests are organized by functionality:
- `test_routes.py` - API endpoint tests
- `test_service.py` - Business logic tests
- `test_worker.py` - Worker execution tests
- `test_database.py` - Database operations
- `test_auth.py` - Authentication and authorization

All tests use in-memory SQLite databases and isolated test clients.

## Future Enhancements

- Job pagination endpoints
- Job filtering and search
- Job priority management
- Worker health monitoring
- Metrics and monitoring integration
- Rate limiting for job creation

## Contributing

1. Follow existing code patterns
2. Maintain test coverage ≥90%
3. Use type hints for all public APIs
4. Format code with ruff before committing
5. Update documentation for new features
