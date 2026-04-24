from __future__ import annotations

from contextlib import asynccontextmanager

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential
from fastapi import FastAPI

from app.config import get_settings
from app.routers import webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    credential = DefaultAzureCredential(managed_identity_client_id=settings.azure_client_id)
    cosmos_client = CosmosClient(settings.cosmos_endpoint, credential=credential)
    database = cosmos_client.get_database_client("travelbot")
    container = database.get_container_client("trips")

    app.state.cosmos_container = container
    app.state.credential = credential
    app.state.settings = settings

    yield

    await cosmos_client.close()
    await credential.close()


app = FastAPI(title="GroupMe Travel Bot", lifespan=lifespan)
app.include_router(webhook.router)
