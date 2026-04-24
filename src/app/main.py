from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient
from fastapi import FastAPI

from app.config import get_settings
from app.routers import webhook

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    credential = DefaultAzureCredential(managed_identity_client_id=settings.azure_client_id)
    blob_url = f"https://{settings.storage_account_name}.blob.core.windows.net"
    blob_service = BlobServiceClient(blob_url, credential=credential)
    blob_container = blob_service.get_container_client(settings.storage_container_name)

    app.state.blob_container = blob_container
    app.state.credential = credential
    app.state.settings = settings

    yield

    await blob_service.close()
    await credential.close()


app = FastAPI(title="GroupMe Travel Bot", lifespan=lifespan)
app.include_router(webhook.router)
