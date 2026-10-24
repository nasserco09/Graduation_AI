"""Local-only product entry prototype, isolated from the presentation catalog."""
import hashlib
import json
import sqlite3
from backend.category_routing import CATEGORY_LABELS
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, StrictBool
from starlette.concurrency import run_in_threadpool
from backend.demo_catalog import CatalogConflict, DemoCatalog
from backend.catalog_backup import BackupError, CatalogBackups, MAX_BACKUP_BYTES
from backend.image_preprocessing import PREPROCESSING_VERSION, preprocess_image
from backend.request_validation import MAX_IMAGE_BYTES, validate_image_bytes


class ProductDetails(BaseModel):
    name: str
    category: str = ''
    price: str | None = None
    currency: str = 'YER'
    available: StrictBool = True


class RestoreRequest(BaseModel):
    token: str = Field(max_length=128)


def create_demo_catalog_router(engine, database):
    store = DemoCatalog(database, engine.index.d, 'SigLIP2:' + PREPROCESSING_VERSION)
    backups = CatalogBackups(store)
    router = APIRouter(prefix='/api/demo-catalog', tags=['Local demo catalog'])

    def backup_owner(request):
        actor = getattr(request.state,'admin',None)
        if not actor:
            raise HTTPException(401,detail='login_required')
        return actor['csrf_token']

    def backup_error(error):
        return JSONResponse({'detail':error.code,'code':error.code},status_code=error.status,
                            headers={'Cache-Control':'no-store'})

    @router.get('/products/backup')
    def export_backup(request: Request):
        backup_owner(request)
        try:
            content = backups.export()
            return Response(content,media_type='application/zip',headers={
                'Content-Disposition':'attachment; filename="catalog.fashion-catalog.zip"',
                'Cache-Control':'no-store'})
        except BackupError as error:
            return backup_error(error)
        except (OSError,sqlite3.Error):
            return backup_error(BackupError('backup_failed',500))

    @router.get('/products/backups')
    def list_backups(request: Request):
        backup_owner(request)
        try:
            return {'backups':backups.list_recovery()}
        except (OSError,sqlite3.Error):
            return backup_error(BackupError('backup_failed',500))

    @router.get('/products/recovery/{backup_id}')
    def recovery_backup(backup_id: str, request: Request):
        backup_owner(request)
        try:
            return FileResponse(backups.recovery_path(backup_id),media_type='application/zip',
                                filename='before-restore.fashion-catalog.zip',headers={'Cache-Control':'no-store'})
        except BackupError as error:
            return backup_error(error)
        except OSError:
            return backup_error(BackupError('backup_failed',500))

    @router.post('/products/restore/preview')
    async def preview_backup(request: Request, backup: UploadFile = File(...)):
        owner = backup_owner(request)
        try:
            content = await backup.read(MAX_BACKUP_BYTES+1)
            return await run_in_threadpool(backups.preview,content,owner)
        except BackupError as error:
            return backup_error(error)
        except (OSError,sqlite3.Error):
            return backup_error(BackupError('backup_failed',500))

    @router.post('/products/restore')
    async def restore_backup(request: Request, payload: RestoreRequest):
        owner = backup_owner(request)
        try:
            return await run_in_threadpool(backups.restore,payload.token,owner)
        except BackupError as error:
            return backup_error(error)
        except (OSError,sqlite3.Error):
            return backup_error(BackupError('restore_failed',500))

    def encode(image):
        prepared, _ = preprocess_image(image)
        with engine._index_lock:
            return engine.encode_image(prepared)

    @router.get('/products')
    def list_products():
        return {'products':store.list_products(), 'scope':'isolated_local_demo_catalog'}

    @router.post('/products', status_code=201)
    async def add_product(name: str = Form(...), images: list[UploadFile] = File(...), category: str = Form(''), price: str = Form(''), currency: str = Form('YER'), available: bool = Form(True)):
        try:
            store.details(name,category,price,currency,available)
            if not 1 <= len(images) <= 5:raise ValueError('Upload 1 to 5 images for one product')
            photos = []
            for image in images:
                photos.append(validate_image_bytes(await image.read(MAX_IMAGE_BYTES+1),image.content_type))
            return await run_in_threadpool(store.add,name,photos,encode,category,price,currency,available)
        except ValueError as error:
            raise HTTPException(400,detail=str(error)) from error

    @router.put('/products/{product_id}')
    def update_product(product_id: str, details: ProductDetails):
        try:
            return store.update(product_id, **details.model_dump())
        except KeyError as error:
            raise HTTPException(404,detail='Demo product not found') from error
        except ValueError as error:
            raise HTTPException(400,detail=str(error)) from error

    @router.get('/images/{image_id}')
    def get_image(image_id: str):
        try:return Response(store.image_bytes(image_id),media_type='image/jpeg')
        except KeyError:raise HTTPException(404,detail='Demo catalog image not found')

    @router.put('/products/{product_id}/content')
    async def save_product(product_id: str, name: str = Form(...),
                           image_order: str = Form(...), images: list[UploadFile] = File(default=[]),
                           category: str = Form(''), price: str = Form(''),
                           currency: str = Form('YER'), available: bool = Form(True),
                           revision: int = Form(..., ge=1)):
        try:
            store.details(name, category, price, currency, available)
            order = json.loads(image_order)
            if len(images) > 5:
                raise ValueError('Upload at most 5 images')
            photos = [validate_image_bytes(await image.read(MAX_IMAGE_BYTES+1), image.content_type)
                      for image in images]
            return await run_in_threadpool(store.save, product_id, name, order, photos, encode,
                                           category, price, currency, available, revision)
        except KeyError as error:
            raise HTTPException(404, detail='Demo product not found') from error
        except CatalogConflict as error:
            raise HTTPException(409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(400, detail=str(error)) from error

    @router.delete('/products/{product_id}')
    def delete_product(product_id: str, revision: int):
        try:
            return store.delete(product_id, revision)
        except KeyError as error:
            raise HTTPException(404, detail='Demo product not found') from error
        except CatalogConflict as error:
            raise HTTPException(409, detail=str(error)) from error

    @router.post('/search')
    async def search(image: UploadFile = File(...), top_k: int = 8, category: str = Form('')):
        try:
            if not 1<=top_k<=50:raise ValueError('top_k must be between 1 and 50')
            content = await image.read(MAX_IMAGE_BYTES+1)
            photo=validate_image_bytes(content,image.content_type)
            vector=await run_in_threadpool(encode,photo)
            results, routing=await run_in_threadpool(store.search_with_routing,vector,top_k,category)
            for result in results:
                result['category_label'] = CATEGORY_LABELS.get(result['category'], '')
            return {'results':results,'scope':'isolated_local_demo_catalog',
                    'query': {'sha256': hashlib.sha256(content).hexdigest(),
                              'catalog_source': 'added_products',
                              'category_routing': routing}}
        except ValueError as error:
            raise HTTPException(400,detail=str(error)) from error

    return router
