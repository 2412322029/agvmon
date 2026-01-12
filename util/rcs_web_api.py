import base64

import httpx


def dict2formdata(j: dict):
    temp = []
    for k, v in j.items():
        temp.append(f"{k}={v}")
    return "&".join(temp)


client = httpx.Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
)

baseurl = "http://172.18.2.72:8182/rcms/web"
response = client.post(
    baseurl + "/login/login.action",
    data=dict2formdata(
        {
            "ecsUserName": "lll",
            "ecsPassword": "2f442332cbc52e237752402aeb41ddb3",
            "pwdSafeLevelLogin": "3",
        }
    ),
    cookies={
        "HIK_COOKIE": "19BAF7F71E1SX95",
        "SESSIONID": "D4EA21A6B5F5E5FB4FF1329691936803",
    },
)
print(response.json())

response0 = client.post(
    baseurl + "/transTask/findSubTasksDetail.action",
    data=dict2formdata(
        {
            "transTaskNum": "MFAGV3002026011208003876632HS",
            "searchYear": 2020,
            "showHisData": "false",
        }
    ),
)
print(response0.json())
