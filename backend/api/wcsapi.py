from fastapi import APIRouter, Body

from util.wcs import Wcs

wcs_web_router = APIRouter(
    prefix="/wcs",
    tags=["wcs"],
)
wcs = Wcs()

@wcs_web_router.get("/searchDeviceStatusInfo")
async def search_device_status_info(cms_index: str, device_type: str):

    return await wcs.search_device_status_info(cms_index, device_type)
