import httpx

from util.config import cfg


class Wcs:
    def __init__(
        self, base_url=cfg.get("rcms.wcs_rest_api") + "/wcs/services/rest/cms"
    ):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            },
        )

    async def search_device_status_info(self, cms_index: str, device_type: str):
        # BUFFER  EQ  STK CV
        url = self.base_url + "/searchDeviceStatusInfo"
        data = {
            "cmsIndex": cms_index,
            "deviceType": device_type,
            "needPage": 0,
            "pageSize": 0,
            "portLayer": 1,
            "startPage": 0,
        }
        if cfg.get("test"):
            return test.get(device_type, {})
        try:
            resp = await self.client.post(url, json=data, timeout=5)
            data = resp.json()
            if not data or data.get("code") != 0:
                return {"code": -1, "message": data.get("message", "data is empty")}
            return data
        except httpx.ReadTimeout:
            return {"code": -1, "message": "访问超时"}
        except Exception as e:
            return {"code": -1, "message": str(e)}


test = {
    "STK": {
        "code": 0,
        "message": "",
        "params": {
            "deviceType": "STK",
            "status": [
                {
                    "cmsIndex": "600501",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "600502",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "600501",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "600502",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
            ],
        },
    },
    "BUFFER": {
        "code": 0,
        "message": "",
        "params": {
            "deviceType": "BUFFER",
            "status": [
                {
                    "cmsIndex": "203001",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                    "trayId": "P8000118A2MH080108532",
                },
                {
                    "cmsIndex": "203002",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203003",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203004",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000037A2MD052930263",
                },
                {
                    "cmsIndex": "203005",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000118A2MH073098277",
                },
                {
                    "cmsIndex": "203006",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203001",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000118A2MH021665375",
                },
                {
                    "cmsIndex": "203002",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "B8000037A2MF081409030",
                },
                {
                    "cmsIndex": "203003",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203004",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203005",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203006",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203007",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000118A2MH080121308",
                },
                {
                    "cmsIndex": "203008",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203009",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000118A2MH021676555",
                },
                {
                    "cmsIndex": "203010",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203011",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203012",
                    "manualOp": "00",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203007",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000037A2MD080475870",
                },
                {
                    "cmsIndex": "203008",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203009",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203010",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000118A2MH021664520",
                },
                {
                    "cmsIndex": "203011",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "IN",
                },
                {
                    "cmsIndex": "203012",
                    "manualOp": "00",
                    "portPos": "UP",
                    "present": "ON",
                    "service": "IN",
                    "trayId": "P8000118A2MH080117000",
                },
            ],
        },
    },
    "EQ": {
        "code": 0,
        "message": "",
        "params": {
            "deviceType": "EQ",
            "status": [
                {
                    "cmsIndex": "503101",
                    "eqRequest": "U_REQ",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "IN",
                }
            ],
        },
    },
    "CV": {
        "code": 0,
        "message": "",
        "params": {
            "deviceType": "CV",
            "status": [
                {
                    "cmsIndex": "300201",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "OUT",
                },
                {
                    "cmsIndex": "300205",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "OUT",
                },
                {
                    "cmsIndex": "300201",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "OUT",
                },
                {
                    "cmsIndex": "300205",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "OUT",
                },
                {
                    "cmsIndex": "300206",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "OUT",
                },
                {
                    "cmsIndex": "300210",
                    "portPos": "DOWN",
                    "present": "OFF",
                    "service": "OUT",
                },
                {
                    "cmsIndex": "300206",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "OUT",
                },
                {
                    "cmsIndex": "300210",
                    "portPos": "UP",
                    "present": "OFF",
                    "service": "OUT",
                },
            ],
        },
    },
}
