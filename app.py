import logging
import os
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("blob_api")

app = FastAPI()

# SSL verification: set VERIFY_SSL=false to disable, or set CA_BUNDLE=/path/to/cert.pem
_verify_ssl_env = os.environ.get("VERIFY_SSL", "true").lower()
if _verify_ssl_env == "false":
    SSL_VERIFY = False
    logger.warning("SSL verification is DISABLED — all certificates will be accepted without validation")
elif os.environ.get("CA_BUNDLE"):
    SSL_VERIFY = os.environ["CA_BUNDLE"]  # path to your corporate CA cert
    logger.info("SSL verification using custom CA bundle: %s", SSL_VERIFY)
    try:
        import ssl
        ctx = ssl.create_default_context(cafile=SSL_VERIFY)
        der_certs = ctx.get_ca_certs(binary_form=True)
        logger.info("CA bundle loaded: %d certificate(s) found", len(der_certs))
        for i, der in enumerate(der_certs):
            cert = ssl.DER_cert_to_PEM_cert(der)
            x509 = ssl.PEM_cert_to_DER_cert(cert)
            import hashlib
            sha1 = hashlib.sha1(x509).hexdigest().upper()
            formatted = ":".join(sha1[j:j+2] for j in range(0, len(sha1), 2))
            logger.info("  [%d] SHA1 fingerprint: %s", i + 1, formatted)
    except Exception as e:
        logger.warning("Could not inspect CA bundle: %s", e)
else:
    SSL_VERIFY = True
    import ssl
    import certifi
    try:
        ca_path = certifi.where()
    except Exception:
        ca_path = ssl.get_default_verify_paths().cafile or ssl.get_default_verify_paths().capath or "system default"
    logger.info("SSL verification enabled — using default CA bundle: %s", ca_path)

# Simple in-memory token cache: {cache_key: (token, expires_at)}
_token_cache: dict[str, tuple[str, float]] = {}


def _get_access_token() -> str:
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]
    scope = "https://storage.azure.com/.default"
    cache_key = f"{tenant_id}:{client_id}"

    cached = _token_cache.get(cache_key)
    if cached and time.time() < cached[1] - 60:
        logger.debug("Using cached access token")
        return cached[0]

    logger.info("Fetching new access token from Azure AD")
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    with httpx.Client(verify=SSL_VERIFY) as client:
        resp = client.post(url, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        })
    if resp.status_code != 200:
        logger.error("Token fetch failed: %s %s", resp.status_code, resp.text)
        raise RuntimeError(f"Token fetch failed {resp.status_code}: {resp.text}")

    body = resp.json()
    token = body["access_token"]
    expires_at = time.time() + int(body.get("expires_in", 3600))
    _token_cache[cache_key] = (token, expires_at)
    logger.info("Access token fetched and cached (expires in %ss)", body.get("expires_in", 3600))
    return token


def _blob_url(blob_name: str) -> str:
    account = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
    container = os.environ["AZURE_STORAGE_CONTAINER_NAME"]
    return f"https://{account}.blob.core.windows.net/{container}/{blob_name}"


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "x-ms-version": "2020-10-02",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.put("/blobs/{blob_name:path}", status_code=201)
async def upload_blob(blob_name: str, request: Request):
    data = await request.body()
    if not data:
        logger.warning("Upload rejected for '%s': empty request body", blob_name)
        raise HTTPException(status_code=400, detail="Request body is empty")

    content_type = request.headers.get("content-type", "application/octet-stream")
    logger.info("Uploading blob '%s' (%d bytes, %s)", blob_name, len(data), content_type)

    headers = {
        **_auth_headers(),
        "x-ms-blob-type": "BlockBlob",
        "Content-Type": content_type,
    }

    async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
        resp = await client.put(_blob_url(blob_name), content=data, headers=headers)

    if resp.status_code not in (200, 201):
        logger.error("Upload failed for '%s': %s %s", blob_name, resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    logger.info("Blob '%s' uploaded successfully", blob_name)
    return {"message": f"Blob '{blob_name}' uploaded", "bytes": len(data)}


@app.get("/blobs/{blob_name:path}")
async def download_blob(blob_name: str):
    logger.info("Downloading blob '%s'", blob_name)

    async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
        resp = await client.get(_blob_url(blob_name), headers=_auth_headers())

    if resp.status_code == 404:
        logger.warning("Blob '%s' not found", blob_name)
        raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")
    if resp.status_code != 200:
        logger.error("Download failed for '%s': %s %s", blob_name, resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    content_type = resp.headers.get("content-type", "application/octet-stream")
    logger.info("Blob '%s' downloaded successfully (%d bytes)", blob_name, len(resp.content))
    return Response(content=resp.content, media_type=content_type)


@app.delete("/blobs/{blob_name:path}")
async def delete_blob(blob_name: str):
    logger.info("Deleting blob '%s'", blob_name)

    async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
        resp = await client.delete(_blob_url(blob_name), headers=_auth_headers())

    if resp.status_code == 404:
        logger.warning("Blob '%s' not found", blob_name)
        raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")
    if resp.status_code not in (200, 202):
        logger.error("Delete failed for '%s': %s %s", blob_name, resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    logger.info("Blob '%s' deleted successfully", blob_name)
    return {"message": f"Blob '{blob_name}' deleted"}
