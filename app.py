import os

from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from asgiref.wsgi import WsgiToAsgi
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__)


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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/blobs/<path:blob_name>", methods=["PUT"])
def upload_blob(blob_name: str):
    """Upload data to Azure Blob Storage.

    Body: raw bytes or JSON
    Headers: Content-Type is preserved on the blob.
    """
    data = request.get_data()
    if not data:
        return jsonify({"error": "Request body is empty"}), 400

    content_type = request.content_type or "application/octet-stream"

    try:
        client = _get_blob_client(blob_name)
        client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return jsonify({"message": f"Blob '{blob_name}' uploaded", "bytes": len(data)}), 201
    except AzureError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/blobs/<path:blob_name>", methods=["GET"])
def download_blob(blob_name: str):
    """Download a blob from Azure Blob Storage."""
    try:
        client = _get_blob_client(blob_name)
        props = client.get_blob_properties()
        content_type = props.content_settings.content_type or "application/octet-stream"
        data = client.download_blob().readall()
        return data, 200, {"Content-Type": content_type}
    except ResourceNotFoundError:
        return jsonify({"error": f"Blob '{blob_name}' not found"}), 404
    except AzureError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/blobs/<path:blob_name>", methods=["DELETE"])
def delete_blob(blob_name: str):
    """Delete a blob from Azure Blob Storage."""
    try:
        client = _get_blob_client(blob_name)
        client.delete_blob()
        return jsonify({"message": f"Blob '{blob_name}' deleted"}), 200
    except ResourceNotFoundError:
        return jsonify({"error": f"Blob '{blob_name}' not found"}), 404
    except AzureError as e:
        return jsonify({"error": str(e)}), 500


# Wrap WSGI app for Uvicorn (ASGI server)
asgi_app = WsgiToAsgi(app)

if __name__ == "__main__":
    # Run directly with Flask dev server (not Uvicorn)
    app.run(debug=True, port=8000)
