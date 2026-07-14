import asyncio
import logging
import os
import shutil
from typing import Optional

import aiohttp
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from open_webui.config import CACHE_DIR
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import AIOHTTP_CLIENT_SESSION_SSL
from open_webui.events import EVENTS, publish_event
from open_webui.models.config import Config
from open_webui.routers.openai import get_all_models_responses
from open_webui.utils.auth import get_admin_user
from open_webui.storage.provider import get_pipeline_storage_provider
from pydantic import BaseModel
from starlette.responses import FileResponse

log = logging.getLogger(__name__)


##################################
#
# Pipeline Middleware
# Every hand this passes through can corrupt it or
# improve it. Let each stage leave it better than it found.
#
##################################


def get_sorted_filters(model_id, models):
    filters = [
        model
        for model in models.values()
        if 'pipeline' in model
        and 'type' in model['pipeline']
        and model['pipeline']['type'] == 'filter'
        and (
            model['pipeline']['pipelines'] == ['*']
            or any(model_id == target_model_id for target_model_id in model['pipeline']['pipelines'])
        )
    ]
    sorted_filters = sorted(filters, key=lambda x: x['pipeline']['priority'])
    return sorted_filters


async def get_openai_connection(url_idx: int) -> tuple[str, str]:
    base_urls = await Config.get('openai.api_base_urls', [])
    api_keys = await Config.get('openai.api_keys', [])
    return base_urls[url_idx], api_keys[url_idx]


async def process_pipeline_inlet_filter(request, payload, user, models):
    user = {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role}
    model_id = payload['model']
    sorted_filters = get_sorted_filters(model_id, models)
    model = models[model_id]

    if 'pipeline' in model:
        sorted_filters.append(model)

    async with aiohttp.ClientSession(trust_env=True) as session:
        for filter in sorted_filters:
            urlIdx = filter.get('urlIdx')

            try:
                urlIdx = int(urlIdx)
            except Exception:
                continue

            url, key = await get_openai_connection(urlIdx)

            if not key:
                continue

            headers = {'Authorization': f'Bearer {key}'}
            request_data = {
                'user': user,
                'body': payload,
            }

            try:
                async with session.post(
                    f'{url}/{filter["id"]}/filter/inlet',
                    headers=headers,
                    json=request_data,
                    ssl=AIOHTTP_CLIENT_SESSION_SSL,
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
            except aiohttp.ClientResponseError as e:
                try:
                    res = await response.json() if 'application/json' in response.content_type else {}
                    if 'detail' in res:
                        raise HTTPException(
                            status_code=response.status,
                            detail=res['detail'],
                        )
                except HTTPException:
                    raise
                except Exception:
                    pass

                raise HTTPException(
                    status_code=response.status,
                    detail=e.message,
                )
            except HTTPException:
                raise
            except Exception as e:
                log.exception(f'Connection error: {e}')

    return payload


async def process_pipeline_outlet_filter(request, payload, user, models):
    user = {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role}
    model_id = payload['model']
    sorted_filters = get_sorted_filters(model_id, models)
    model = models[model_id]

    if 'pipeline' in model:
        sorted_filters = [model] + sorted_filters

    async with aiohttp.ClientSession(trust_env=True) as session:
        for filter in sorted_filters:
            urlIdx = filter.get('urlIdx')

            try:
                urlIdx = int(urlIdx)
            except Exception:
                continue

            url, key = await get_openai_connection(urlIdx)

            if not key:
                continue

            headers = {'Authorization': f'Bearer {key}'}
            request_data = {
                'user': user,
                'body': payload,
            }

            try:
                async with session.post(
                    f'{url}/{filter["id"]}/filter/outlet',
                    headers=headers,
                    json=request_data,
                    ssl=AIOHTTP_CLIENT_SESSION_SSL,
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
            except aiohttp.ClientResponseError as e:
                try:
                    res = await response.json() if 'application/json' in response.content_type else {}
                    if 'detail' in res:
                        raise HTTPException(
                            status_code=response.status,
                            detail=res['detail'],
                        )
                except HTTPException:
                    raise
                except Exception:
                    pass

                raise HTTPException(
                    status_code=response.status,
                    detail=e.message,
                )
            except HTTPException:
                raise
            except Exception as e:
                log.exception(f'Connection error: {e}')

    return payload


##################################
#
# Pipelines Endpoints
#
##################################

router = APIRouter()


@router.get('/list')
async def get_pipelines_list(request: Request, user=Depends(get_admin_user)):
    responses = await get_all_models_responses(request, user)
    log.debug(f'get_pipelines_list: get_openai_models_responses returned {responses}')

    urlIdxs = [idx for idx, response in enumerate(responses) if response is not None and 'pipelines' in response]
    base_urls = await Config.get('openai.api_base_urls', [])

    return {
        'data': [
            {
                'url': base_urls[urlIdx],
                'idx': urlIdx,
            }
            for urlIdx in urlIdxs
        ]
    }


@router.post('/upload')
async def upload_pipeline(
    request: Request,
    urlIdx: int = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_admin_user),
):
    log.info(f'upload_pipeline: urlIdx={urlIdx}, filename={file.filename}')
    filename = os.path.basename(file.filename)

    # Check if the uploaded file is a python file
    if not (filename and filename.endswith('.py')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only Python (.py) files are allowed.',
        )

    upload_folder = f'{CACHE_DIR}/pipelines'
    os.makedirs(upload_folder, exist_ok=True)
    # Use .tmp extension to prevent uvicorn --reload from detecting the .py file
    # and triggering a server restart that crashes the backend
    file_path = os.path.join(upload_folder, f"{filename}.tmp")

    try:
        # Save the uploaded file locally (temp)
        with open(file_path, 'wb') as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Upload directly to Azure Blob Storage (pipeline container)
        # NOTE: We intentionally avoid pipeline_storage.upload_file() here because
        # AzureStorageProvider.upload_file() calls LocalStorageProvider.upload_file()
        # which saves the .py file to data/uploads/, triggering uvicorn --reload
        # and crashing the dev server.
        try:
            pipeline_storage = get_pipeline_storage_provider()
            with open(file_path, 'rb') as f:
                contents = f.read()
            blob_client = pipeline_storage.container_client.get_blob_client(filename)
            blob_client.upload_blob(contents, overwrite=True)
            log.info(f"Pipeline file '{filename}' uploaded to Azure Blob Storage")
        except Exception as e:
            log.warning(f'Failed to upload pipeline to Azure Blob Storage: {e}')

        url, key = await get_openai_connection(urlIdx)

        headers = {'Authorization': f'Bearer {key}'}

        detail = None
        resp_status = None

        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(
                trust_env=True, timeout=timeout
            ) as session:
                with open(file_path, 'rb') as f:
                    form_data = aiohttp.FormData()
                    form_data.add_field(
                        'file',
                        f,
                        filename=filename,
                        content_type='application/octet-stream',
                    )

                    async with session.post(
                        f'{url}/pipelines/upload',
                        headers=headers,
                        data=form_data,
                        ssl=AIOHTTP_CLIENT_SESSION_SSL,
                    ) as response:
                        resp_status = response.status
                        data = await response.json()
                        if response.ok:
                            return {**data}
                        # Extract error detail while response is still open
                        if 'detail' in data:
                            detail = data['detail']
        except aiohttp.ClientConnectionError as e:
            log.warning(f'Pipeline server connection error: {e}')
            detail = 'Pipeline server is not reachable. Ensure the pipeline server is running.'
        except asyncio.TimeoutError:
            log.warning('Pipeline server request timed out')
            detail = 'Pipeline server request timed out.'
        except Exception as e:
            log.warning(f'Pipeline upload failed: {e}')
            detail = f'Pipeline upload failed: {e}'

        raise HTTPException(
            status_code=resp_status or status.HTTP_502_BAD_GATEWAY,
            detail=detail or 'Pipeline not found',
        )
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f'Unexpected error during pipeline upload: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Pipeline upload error: {e}',
        )
    finally:
        # Ensure the file is deleted after the upload is completed or on failure
        if os.path.exists(file_path):
            os.remove(file_path)


class AddPipelineForm(BaseModel):
    url: str
    urlIdx: int


@router.post('/add')
async def add_pipeline(request: Request, form_data: AddPipelineForm, user=Depends(get_admin_user)):
    response = None
    try:
        urlIdx = form_data.urlIdx

        url, key = await get_openai_connection(urlIdx)

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                f'{url}/pipelines/add',
                headers={'Authorization': f'Bearer {key}'},
                json={'url': form_data.url},
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                response.raise_for_status()
                data = await response.json()

        await publish_event(
            request,
            EVENTS.PIPELINE_ADDED,
            actor=user,
            subject_id=data.get('id') or form_data.url,
            data={'url_idx': urlIdx, 'url': form_data.url},
        )
        return {**data}
    except Exception as e:
        # Handle connection error here
        log.exception(f'Connection error: {e}')

        detail = None
        if response is not None:
            try:
                res = await response.json()
                if 'detail' in res:
                    detail = res['detail']
            except Exception:
                pass

        raise HTTPException(
            status_code=(response.status if response is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else 'Pipeline not found',
        )


class DeletePipelineForm(BaseModel):
    id: str
    urlIdx: int


@router.delete('/delete')
async def delete_pipeline(request: Request, form_data: DeletePipelineForm, user=Depends(get_admin_user)):
    response = None
    try:
        urlIdx = form_data.urlIdx

        url, key = await get_openai_connection(urlIdx)

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.delete(
                f'{url}/pipelines/delete',
                headers={'Authorization': f'Bearer {key}'},
                json={'id': form_data.id},
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                response.raise_for_status()
                data = await response.json()

        await publish_event(
            request,
            EVENTS.PIPELINE_DELETED,
            actor=user,
            subject_id=form_data.id,
            data={'url_idx': urlIdx},
        )
        return {**data}
    except Exception as e:
        # Handle connection error here
        log.exception(f'Connection error: {e}')

        detail = None
        if response is not None:
            try:
                res = await response.json()
                if 'detail' in res:
                    detail = res['detail']
            except Exception:
                pass

        raise HTTPException(
            status_code=(response.status if response is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else 'Pipeline not found',
        )


@router.get('/')
async def get_pipelines(request: Request, urlIdx: Optional[int] = None, user=Depends(get_admin_user)):
    response = None
    try:
        url, key = await get_openai_connection(urlIdx)

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(
                f'{url}/pipelines',
                headers={'Authorization': f'Bearer {key}'},
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                response.raise_for_status()
                data = await response.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        log.exception(f'Connection error: {e}')

        detail = None
        if response is not None:
            try:
                res = await response.json()
                if 'detail' in res:
                    detail = res['detail']
            except Exception:
                pass

        raise HTTPException(
            status_code=(response.status if response is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else 'Pipeline not found',
        )


@router.get('/{pipeline_id}/valves')
async def get_pipeline_valves(
    request: Request,
    urlIdx: Optional[int],
    pipeline_id: str,
    user=Depends(get_admin_user),
):
    response = None
    try:
        url, key = await get_openai_connection(urlIdx)

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(
                f'{url}/{pipeline_id}/valves',
                headers={'Authorization': f'Bearer {key}'},
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                response.raise_for_status()
                data = await response.json()

        await publish_event(
            request,
            EVENTS.PIPELINE_VALVES_UPDATED,
            actor=user,
            subject_id=pipeline_id,
            data={'url_idx': urlIdx},
        )
        return {**data}
    except Exception as e:
        # Handle connection error here
        log.exception(f'Connection error: {e}')

        detail = None
        if response is not None:
            try:
                res = await response.json()
                if 'detail' in res:
                    detail = res['detail']
            except Exception:
                pass

        raise HTTPException(
            status_code=(response.status if response is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else 'Pipeline not found',
        )


@router.get('/{pipeline_id}/valves/spec')
async def get_pipeline_valves_spec(
    request: Request,
    urlIdx: Optional[int],
    pipeline_id: str,
    user=Depends(get_admin_user),
):
    response = None
    try:
        url, key = await get_openai_connection(urlIdx)

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(
                f'{url}/{pipeline_id}/valves/spec',
                headers={'Authorization': f'Bearer {key}'},
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                response.raise_for_status()
                data = await response.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        log.exception(f'Connection error: {e}')

        detail = None
        if response is not None:
            try:
                res = await response.json()
                if 'detail' in res:
                    detail = res['detail']
            except Exception:
                pass

        raise HTTPException(
            status_code=(response.status if response is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else 'Pipeline not found',
        )


@router.post('/{pipeline_id}/valves/update')
async def update_pipeline_valves(
    request: Request,
    urlIdx: Optional[int],
    pipeline_id: str,
    form_data: dict,
    user=Depends(get_admin_user),
):
    response = None
    try:
        url, key = await get_openai_connection(urlIdx)

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                f'{url}/{pipeline_id}/valves/update',
                headers={'Authorization': f'Bearer {key}'},
                json={**form_data},
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                response.raise_for_status()
                data = await response.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        log.exception(f'Connection error: {e}')

        detail = None

        if response is not None:
            try:
                res = await response.json()
                if 'detail' in res:
                    detail = res['detail']
            except Exception:
                pass

        raise HTTPException(
            status_code=(response.status if response is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else 'Pipeline not found',
        )
