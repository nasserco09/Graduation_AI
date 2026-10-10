"""Local-only product entry prototype, isolated from the presentation catalog."""
import hashlib
from backend.category_routing import CATEGORY_LABELS
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, StrictBool
from starlette.concurrency import run_in_threadpool
from backend.demo_catalog import DemoCatalog
from backend.image_preprocessing import PREPROCESSING_VERSION, preprocess_image
from backend.request_validation import MAX_IMAGE_BYTES, validate_image_bytes


class ProductDetails(BaseModel):
    name: str
    category: str = ''
    price: str | None = None
    currency: str = 'YER'
    available: StrictBool = True


def create_demo_catalog_router(engine, database):
    store = DemoCatalog(database, engine.index.d, 'SigLIP2:' + PREPROCESSING_VERSION)
    router = APIRouter(prefix='/api/demo-catalog', tags=['Local demo catalog'])

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
