class AGVProtocolParser {
  constructor() {
    this.protocolConfig = {
      fixedHeader: [0x05, 0x06],
      portStructure: {
        statusByteCount: 4, // 4个状态字节
        trayIdByteCount: 50, // 50个TrayId字节
        totalPerPort: 54, // 每个Port总共54字节
      },
    };
  }

  parseEQStatus(data) {
    try {
      let buffer = this._preprocessData(data);
      if (!buffer) {
        throw new Error("无效的数据格式");
      }

      if (buffer.length < 6) {
        throw new Error("数据长度不足，至少需要6字节");
      }

      if (buffer[0] !== 0x05 || buffer[1] !== 0x06) {
        throw new Error("无效的协议头，应为0x05 0x06");
      }

      const dataLengthHigh = buffer[2];
      const dataLengthLow = buffer[3];
      const declaredLength = (dataLengthHigh << 8) | dataLengthLow;

      const result = {
        header: {
          fixed1: buffer[0],
          fixed2: buffer[1],
          declaredLength: declaredLength,
          actualLength: buffer.length,
        },
        status: this._parseStatus(buffer),
        ports: [],
        rawData: this._toHexString(buffer),
        isValid: true,
        warnings: [],
      };

      // 使用实际缓冲区长度计算可用数据长度
      const availableDataLength = buffer.length - 6;

      if (availableDataLength > 0) {
        const maxPortCount = Math.floor(
          availableDataLength / this.protocolConfig.portStructure.totalPerPort
        );

        for (let i = 0; i < maxPortCount; i++) {
          const portOffset =
            6 + i * this.protocolConfig.portStructure.totalPerPort;
          if (
            portOffset + this.protocolConfig.portStructure.totalPerPort <=
            buffer.length
          ) {
            const portData = this._parsePortData(buffer, portOffset, i + 1);
            result.ports.push(portData);
          } else {
            result.warnings.push(
              `Port${i + 1}数据不完整，期望${
                this.protocolConfig.portStructure.totalPerPort
              }字节，实际${buffer.length - portOffset}字节`
            );
            break;
          }
        }

        // 处理剩余数据
        const remainingBytes =
          availableDataLength -
          maxPortCount * this.protocolConfig.portStructure.totalPerPort;
        if (remainingBytes > 0) {
          result.warnings.push(`有${remainingBytes}字节未使用的额外数据`);
        }
      }

      return result;
    } catch (error) {
      return {
        header: {
          fixed1: 0x00,
          fixed2: 0x00,
          declaredLength: 0,
          actualLength: 0,
        },
        status: { errorCode: 0x00, errorText: "未知状态", reserved: 0x00 },
        ports: [],
        rawData: typeof data === "string" ? data.toUpperCase() : "",
        isValid: false,
        warnings: [],
        error: error.message,
      };
    }
  }

  _parseStatus(buffer) {
    const errorCode = buffer[4];
    const errorMap = {
      0x00: "正常",
      0x01: "故障",
      0x02: "急停",
      0x03: "手动",
      0x04: "故障",
    };
    const reservedCode = buffer[5];
    const reservedMap = {
      0x00: "未屏蔽",
      0x01: "已屏蔽",
    };
    return {
      errorCode: errorCode,
      errorText: errorMap[errorCode] || "未知状态",
      reserved: reservedCode,
      reservedText: reservedMap[reservedCode] || "未知状态",
    };
  }

  _parsePortData(buffer, offset, portNumber) {
    // 确保缓冲区足够长
    const safeGetByte = (index) => {
      return buffer.length > index ? buffer[index] : 0x00;
    };

    // Port状态字节（4字节）
    const loadUnloadStatus = safeGetByte(offset);
    const trayPresentStatus = safeGetByte(offset + 1);
    const onlineStatus = safeGetByte(offset + 2);
    const reservedByte = safeGetByte(offset + 3);

    // TrayId起始位置：状态字节后
    const trayIdStart = offset + 4;

    // 提取TrayId的50个字节
    const trayIdBuffer = new Uint8Array(50);
    for (let i = 0; i < 50; i++) {
      trayIdBuffer[i] = safeGetByte(trayIdStart + i);
    }

    const trayId = this._parseTrayId(trayIdBuffer);

    return {
      portNumber: portNumber,
      loadUnload: {
        code: loadUnloadStatus,
        text: this._getLoadUnloadText(loadUnloadStatus),
      },
      trayPresent: {
        code: trayPresentStatus,
        text: this._getTrayPresentText(trayPresentStatus),
      },
      onlineStatus: {
        code: onlineStatus,
        text: this._getOnlineStatusText(onlineStatus),
      },
      reserved: reservedByte,
      trayId: trayId,
      rawData: this._toHexString(
        buffer.slice(offset, Math.min(offset + 54, buffer.length))
      ),
    };
  }

  _getLoadUnloadText(code) {
    switch (code) {
      case 0x01:
        return "LR(上料)";
      case 0x02:
        return "UR(下料)";
      default:
        return "无上/下料任务";
    }
  }

  _getTrayPresentText(code) {
    switch (code) {
      case 0x00:
        return "Present OFF(无tray盘)";
      case 0x01:
        return "Present On(有tray盘)";
      default:
        return "未知状态";
    }
  }

  _getOnlineStatusText(code) {
    switch (code) {
      case 0x00:
        return "Out of Service(离线)";
      case 0x01:
        return "In Service(在线)";
      default:
        return "未知状态";
    }
  }

  _parseTrayId(buffer) {
    let result = "";
    for (let i = 0; i < buffer.length; i++) {
      const byte = buffer[i];
      if (byte >= 0x20 && byte <= 0x7e) {
        result += String.fromCharCode(byte);
      } else if (byte === 0x00 || byte === 0x20) {
        // 遇到空格或0x00，继续检查是否有后续字符
        continue;
      }
    }
    return result.trim();
  }

  _preprocessData(data) {
    if (typeof data === "string") {
      const cleanHex = data.replace(/[^0-9A-Fa-f]/g, "");
      if (cleanHex.length === 0) throw new Error("空数据");
      if (cleanHex.length % 2 !== 0)
        throw new Error("十六进制字符串长度不正确");

      const buffer = new Uint8Array(cleanHex.length / 2);
      for (let i = 0; i < cleanHex.length; i += 2) {
        buffer[i / 2] = parseInt(cleanHex.substr(i, 2), 16);
      }
      return buffer;
    } else if (data instanceof Uint8Array) {
      return data;
    } else if (Array.isArray(data)) {
      return new Uint8Array(data);
    } else {
      throw new Error(
        "不支持的数据格式，支持: 十六进制字符串、Uint8Array、数组"
      );
    }
  }

  _toHexString(buffer) {
    let hex = "";
    for (let i = 0; i < buffer.length; i++) {
      hex += buffer[i].toString(16).padStart(2, "0").toUpperCase();
    }
    return hex;
  }
}

export default AGVProtocolParser;
