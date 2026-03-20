import os

from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

load_dotenv()

app = FastAPI()


def _get_blob_client(blob_name: str):
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    account_name = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
    container_name = os.environ["AZURE_STORAGE_CONTAINER_NAME"]

    blob_service = BlobServiceClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        credential=credential,
    )
    return blob_service.get_blob_client(container=container_name, blob=blob_name)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.put("/blobs/{blob_name:path}", status_code=201)
async def upload_blob(blob_name: str, request: Request):
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Request body is empty")

    content_type = request.headers.get("content-type", "application/octet-stream")

    try:
        client = _get_blob_client(blob_name)
        client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return {"message": f"Blob '{blob_name}' uploaded", "bytes": len(data)}
    except AzureError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/blobs/{blob_name:path}")
def download_blob(blob_name: str):
    try:
        client = _get_blob_client(blob_name)
        props = client.get_blob_properties()
        content_type = props.content_settings.content_type or "application/octet-stream"
        data = client.download_blob().readall()
        return Response(content=data, media_type=content_type)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")
    except AzureError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/blobs/{blob_name:path}")
def delete_blob(blob_name: str):
    try:
        client = _get_blob_client(blob_name)
        client.delete_blob()
        return {"message": f"Blob '{blob_name}' deleted"}
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Blob '{blob_name}' not found")
    except AzureError as e:
        raise HTTPException(status_code=500, detail=str(e))
