import xmltodict
from fastapi import APIRouter, Request

from util.rcms_api import RcmsApi

rcms_router = APIRouter(
    prefix="/rcms",
    tags=["rcms"],
)

# 创建RcmsApi实例
rapi = RcmsApi()

@rcms_router.get("/build_from_cache")
def build_rcms_from_cache_api():
    try:
        retmsg = rapi.build_from_cache()
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}
    if retmsg:
        return {"message": "error", "errors": retmsg}
    else:
        return {"message": "RCMS cache built successfully"}

@rcms_router.get("/build_from_raw") 
def build_rcms_from_raw_api(request: Request):
    try:
        rapi.fake = request.query_params.get("fake", default=False)
        rapi.build_from_raw()
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}
    retmsg = []
    for i in [rapi.rcsdata, rapi.maplist, rapi.devicelist, rapi.displaytype, rapi.alarmtype]:
        if not i:
            retmsg.append(f"数据为空: {i}")
    if retmsg:
        return {"message": "error", "errors": retmsg}
    else:
        return {"message": "RCMS raw data built successfully"}

# 获取共享地图数据
@rcms_router.get("/sharemapdata")
def get_sharemapdata_api():
    if isinstance(rapi.sharemapdata,str):
        return xmltodict.parse(rapi.sharemapdata)
    return rapi.sharemapdata

@rcms_router.get("/maplist")
def get_maplist_api():
    return rapi.maplist