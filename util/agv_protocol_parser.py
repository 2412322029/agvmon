import re


class AGVProtocolParser:
    FIXED_HEADER = (0x05, 0x06)
    STATUS_BYTES_PER_PORT = 8
    TRAY_ID_BYTES_PER_PORT = 50
    TOTAL_BYTES_PER_PORT = STATUS_BYTES_PER_PORT + TRAY_ID_BYTES_PER_PORT

    STATUS_MAPS: dict[str, dict[int, str]] = {
        "gratingStatus":     {0x00: "未屏蔽", 0x01: "已屏蔽"},
        "readyStatus":       {0x00: "未就绪", 0x01: "已就绪"},
        "trayOkStatus":      {0x00: "未Ok", 0x01: "机台接料Ok", 0x02: "机台送料OK"},
        "onlineStatus":      {0x00: "Out of Service(离线)", 0x01: "In Service(在线)"},
        "trayPresentStatus": {0x00: "Present OFF(无tray盘)", 0x01: "Present On(有tray盘)"},
        "rollerStartStatus": {0x00: "未滚动", 0x01: "机台接料已滚动", 0x02: "机台送料已滚动"},
        "manualOperation":   {0x00: "无操作", 0x01: "绑定，人工放上", 0x02: "解绑，人工拿走"},
        "traySize":          {0x01: "小", 0x02: "大"},
    }

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def parse_eq_status(self, data: str | bytes | bytearray | list[int]) -> dict:
        """Parse PLC device status data (EQ = Equipment)."""
        try:
            buffer = self._preprocess(data)
            if len(buffer) < 6:
                raise ValueError("数据长度不足，至少需要6字节")

            if buffer[0] != 0x05 or buffer[1] != 0x06:
                raise ValueError("无效的协议头，应为0x05 0x06")

            declared_dlen = (buffer[2] << 8) | buffer[3]
            actual_dlen = len(buffer) - 8

            lower_grating = buffer[4]
            upper_grating = buffer[5]

            port_data = buffer[6:]
            port_count = len(port_data) // self.TOTAL_BYTES_PER_PORT

            ports = [
                self._parse_port(buffer, 6 + i * self.TOTAL_BYTES_PER_PORT, i + 1)
                for i in range(port_count)
            ]

            result: dict = {
                "header": {
                    "fixed1": buffer[0],
                    "fixed2": buffer[1],
                    "declaredDataLength": declared_dlen,
                    "actualDataLength": actual_dlen,
                    "isValid": actual_dlen == declared_dlen,
                },
                "gratingStatus": {
                    "lowerGrating": self._label("gratingStatus", lower_grating),
                    "upperGrating": self._label("gratingStatus", upper_grating),
                },
                "portCount": port_count,
                "ports": ports,
                "rawData": self._to_hex(buffer),
                "isValid": True,
                "warnings": [],
            }

            if len(port_data) % self.TOTAL_BYTES_PER_PORT != 0:
                msg = (
                    f"数据长度不完整: Port口数据长度{len(port_data)}"
                    f"不是每个Port口{self.TOTAL_BYTES_PER_PORT}字节的整数倍"
                )
                result["warnings"].append(msg)

            if not result["header"]["isValid"]:
                result["warnings"].append(
                    f"数据长度不匹配: 声明{declared_dlen}字节, 实际{actual_dlen}字节"
                )

            if not ports:
                result["warnings"].append("未解析到有效的Port口数据")

            return result

        except Exception as exc:
            return {
                "header": {"fixed1": 0, "fixed2": 0, "declaredDataLength": 0,
                           "actualDataLength": 0, "isValid": False},
                "gratingStatus": {},
                "portCount": 0,
                "ports": [],
                "rawData": data if isinstance(data, str) else "",
                "isValid": False,
                "warnings": [],
                "error": str(exc),
            }

    def parse_agv_command(self, data: str | bytes | bytearray | list[int]) -> dict:
        """Parse AGV control command."""
        try:
            buffer = self._preprocess(data)

            if len(buffer) < 13:
                raise ValueError("AGV指令数据长度不足")
            if buffer[0] != 0x05 or buffer[1] != 0x06:
                raise ValueError("无效的协议头，应为0x05 0x06")

            data_len = buffer[2]
            if data_len != 0x63:
                import warnings
                warnings.warn(f"AGV指令数据长度异常: 期望0x63, 实际0x{data_len:02X}")

            def text(map: dict[int, str], v: int) -> str:
                return map.get(v, f"未知(0x{v:02X})")

            return {
                "header": {"fixed1": buffer[0], "fixed2": buffer[1], "dataLength": data_len},
                "command": {
                    "commandType": buffer[3],
                    "commandTypeText": text(
                        {0x01: "读指令", 0x02: "控制指令"}, buffer[3]),
                    "layer": buffer[4],
                    "layerText": text(
                        {0x01: "下层", 0x02: "上层"}, buffer[4]),
                    "port1": {
                        "code": buffer[5],
                        "text": f"第{buffer[5]}个Port口" if buffer[5] != 0 else "无（未指定）",
                    },
                    "port2": {
                        "code": buffer[6],
                        "text": f"第{buffer[6]}个Port口" if buffer[6] != 0 else "无（未指定，仅控制一个Port口）",
                    },
                    "agvArrived": self._label_raw(
                        {0x01: "AGV已到达Port口，屏蔽光栅"}, buffer[7]),
                    "rollerAction": self._label_raw(
                        {0x01: "机台接料滚动", 0x02: "机台送料滚动"}, buffer[8]),
                    "agvTrayOk": self._label_raw(
                        {0x01: "AGV接料成功", 0x02: "AGV送料成功"}, buffer[9]),
                    "agvLeave": self._label_raw(
                        {0x01: "AGV离开不恢复光栅", 0x02: "AGV离开恢复光栅"}, buffer[10]),
                    "traySize": self._label_raw(
                        {0x01: "小", 0x02: "大"}, buffer[11]),
                },
                "trayId": self._parse_tray_id(buffer[12:62]),
                "trayId2": self._parse_tray_id(buffer[62:112]) if buffer[6] != 0 else "",
                "rawData": self._to_hex(buffer),
                "isValid": True,
            }

        except Exception as exc:
            return {
                "header": {}, "command": {}, "trayId": "", "trayId2": "",
                "rawData": data if isinstance(data, str) else "",
                "isValid": False, "error": str(exc),
            }

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _label(self, map_name: str, code: int) -> dict:
        m = self.STATUS_MAPS.get(map_name, {})
        return {"code": code, "text": m.get(code, f"未知状态({code})")}

    @staticmethod
    def _label_raw(label_map: dict[int, str], code: int) -> dict:
        return {"code": code, "text": label_map.get(code, f"未知(0x{code:02X})")}

    def _parse_port(self, buffer: bytes, offset: int, port_num: int) -> dict:
        def byte(i: int) -> int:
            return buffer[offset + i] if offset + i < len(buffer) else 0

        tray_id_buf = buffer[offset + 8 : offset + self.TOTAL_BYTES_PER_PORT]
        tray_id_buf = tray_id_buf.ljust(self.TRAY_ID_BYTES_PER_PORT, b"\x00")
        tray_id = self._parse_tray_id(tray_id_buf)

        position = f"下层左{port_num}Port" if port_num <= 2 else f"上层左{port_num - 2}Port"

        return {
            "portNumber": port_num,
            "portPosition": position,
            "status": {
                "readyStatus":       self._label("readyStatus", byte(0)),
                "trayOkStatus":      self._label("trayOkStatus", byte(1)),
                "onlineStatus":      self._label("onlineStatus", byte(2)),
                "trayPresentStatus": self._label("trayPresentStatus", byte(3)),
                "rollerStartStatus": self._label("rollerStartStatus", byte(4)),
                "reserved":          {"code": byte(5), "text": "预留" if byte(5) == 0 else f"未知预留值: 0x{byte(5):04X}"},
                "manualOperation":   self._label("manualOperation", byte(6)),
                "traySize":          self._label("traySize", byte(7)),
            },
            "trayId": tray_id,
            "rawData": self._to_hex(buffer[offset : offset + self.TOTAL_BYTES_PER_PORT]),
        }

    @staticmethod
    def _parse_tray_id(buffer: bytes) -> str:
        result = ""
        has_value = False
        for b in buffer:
            if b not in (0x00, 0x20):
                has_value = True
            if 0x20 <= b <= 0x7E:
                result += chr(b)
            else:
                result += " "
        if not has_value:
            return "无"
        trimmed = re.sub(r"\s+", "", result.rstrip(" "))
        return trimmed or "00"

    @staticmethod
    def _preprocess(data: str | bytes | bytearray | list[int]) -> bytes:
        if isinstance(data, str):
            clean = re.sub(r"[^0-9A-Fa-f]", "", data)
            if not clean:
                raise ValueError("空数据")
            if len(clean) % 2 != 0:
                raise ValueError("十六进制字符串长度不正确")
            return bytes.fromhex(clean)
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, list):
            return bytes(data)
        raise TypeError("不支持的数据格式，支持: 十六进制字符串、bytes、bytearray、list[int]")

    @staticmethod
    def _to_hex(buffer: bytes) -> str:
        return buffer.hex().upper()
