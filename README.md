# Azure Blob Storage REST API

A lightweight FastAPI service for uploading, downloading, and deleting blobs in Azure Blob Storage. Uses direct Azure REST API calls (no Azure SDK) with Service Principal authentication.

## Features

- Upload, download, and delete blobs
- Service Principal (client credentials) OAuth2 authentication
- In-memory token caching (auto-refreshes before expiry)
- Configurable SSL verification for corporate proxy environments
- Structured logging with SSL/cert details at startup

## Requirements

- Python 3.10+
- Azure Storage Account
- Azure AD Service Principal with `Storage Blob Data Contributor` role on the container

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd flask-azure-api
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_STORAGE_ACCOUNT_NAME=yourstorageaccount
AZURE_STORAGE_CONTAINER_NAME=your-container
```

### 3. Run

```bash
uvicorn app:app --reload
```

API will be available at `http://localhost:8000`.
Interactive docs at `http://localhost:8000/docs`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `PUT` | `/blobs/{blob_name}` | Upload a blob |
| `GET` | `/blobs/{blob_name}` | Download a blob |
| `DELETE` | `/blobs/{blob_name}` | Delete a blob |

`{blob_name}` supports nested paths, e.g. `folder/subfolder/file.txt`.

### Examples

```bash
# Health check
curl http://localhost:8000/health

# Upload
curl -X PUT http://localhost:8000/blobs/hello.txt \
  -H "Content-Type: text/plain" \
  --data "hello world"

# Upload a file
curl -X PUT http://localhost:8000/blobs/image.png \
  -H "Content-Type: image/png" \
  --data-binary @image.png

# Download
curl http://localhost:8000/blobs/hello.txt

# Delete
curl -X DELETE http://localhost:8000/blobs/hello.txt
```

## SSL Configuration

The service supports three SSL modes, controlled via environment variables:

| Setting | Behavior |
|---------|----------|
| `VERIFY_SSL=true` (default) | Uses certifi's CA bundle |
| `CA_BUNDLE=/path/to/cert.pem` | Uses your corporate CA certificate |
| `VERIFY_SSL=false` | Disables SSL verification (not recommended for production) |

### Corporate Proxy / Self-signed Cert

If you're behind a corporate proxy that intercepts SSL, append your corporate CA to the certifi bundle:

```bash
# Find bundle location
python -c "import certifi; print(certifi.where())"

# Append corporate CA
cat your-corp-ca.pem >> /path/to/certifi/cacert.pem
```

Or set `CA_BUNDLE` in your `.env` to point to a combined PEM file. Startup logs will show the SHA1 fingerprint of each loaded certificate for verification.
