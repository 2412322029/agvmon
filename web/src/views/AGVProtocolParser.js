class AGVProtocolParser {
  constructor() {
    this.protocolConfig = {
      fixedHeader: [0x05, 0x06],
      // 每个Port口的数据结构（根据文档）
      portStructure: {
        // 每个Port口的状态变量数量（从文档中的变量序号计算）
        // 从7到14是8个状态变量，每个int16(2字节)，共16字节
        statusBytesPerPort: 8 , // 8字节
        // TrayId: 50个字节
        trayIdBytesPerPort: 50, // 50字节
        // 每个Port口总字节数
        totalBytesPerPort: 8  + 50, // 58字节
        // Port口数量（根据文档示例是4个）
        defaultPortCount: 4
      }
    };
    
    // 状态映射表
    this.statusMaps = {
      // 光栅状态
      gratingStatus: {
        0x00: '未屏蔽',
        0x01: '已屏蔽'
      },
      // 就绪状态
      readyStatus: {
        0x00: '未就绪',
        0x01: '已就绪'
      },
      // TrayOk状态
      trayOkStatus: {
        0x00: '未Ok',
        0x01: '机台接料Ok',
        0x02: '机台送料OK'
      },
      // 设备在线状态
      onlineStatus: {
        0x00: 'Out of Service(离线)',
        0x01: 'In Service(在线)'
      },
      // 有无tray盘状态
      trayPresentStatus: {
        0x00: 'Present OFF(无tray盘)',
        0x01: 'Present On(有tray盘)'
      },
      // Roller start状态
      rollerStartStatus: {
        0x00: '未滚动',
        0x01: '机台接料已滚动',
        0x02: '机台送料已滚动'
      },
      // 人工操作
      manualOperation: {
        0x00: '无操作',
        0x01: '绑定，人工放上',
        0x02: '解绑，人工拿走'
      },
      // TraySize
      traySize: {
        0x01: '小',
        0x02: '大'
      }
    };
  }

  /**
   * 解析PLC设备状态数据
   * @param {string|Uint8Array|Array} data - 原始数据
   * @returns {Object} 解析结果
   */
  parseEQStatus(data) {
    try {
      // 1. 预处理数据
      let buffer = this._preprocessData(data);
      if (!buffer) {
        throw new Error("无效的数据格式");
      }

      // 2. 基本校验
      if (buffer.length < 6) {
        throw new Error("数据长度不足，至少需要6字节");
      }

      // 3. 校验协议头
      if (buffer[0] !== 0x05 || buffer[1] !== 0x06) {
        throw new Error("无效的协议头，应为0x05 0x06");
      }

      // 4. 解析数据长度
      const dataLengthHigh = buffer[2];
      const dataLengthLow = buffer[3];
      const declaredDataLength = (dataLengthHigh << 8) | dataLengthLow;
      
      // 计算实际数据部分长度（从字节5开始）
      const actualDataLength = buffer.length - 8; // 减去固定头和数据长度字节和光栅状态部分
      
      // 5. 解析全局状态（光栅状态）
      const lowerGrating = buffer[4];  // 字节5: 下层光栅
      const upperGrating = buffer[5];  // 字节6: 上层光栅
      
      // 6. 计算Port口数量
      const portDataStart = 6; // Port口数据从字节7开始
      const portDataLength = buffer.length - 6
      const portCount = Math.floor(portDataLength / this.protocolConfig.portStructure.totalBytesPerPort);
      
      // 8. 解析所有Port口数据
      const ports = [];
      for (let i = 0; i < portCount; i++) {
        const portOffset = portDataStart + (i * this.protocolConfig.portStructure.totalBytesPerPort);
        const portData = this._parsePortData(buffer, portOffset, i + 1);
        ports.push(portData);
      }

      // 9. 构建结果
      const result = {
        header: {
          fixed1: buffer[0],
          fixed2: buffer[1],
          declaredDataLength: declaredDataLength,
          actualDataLength: actualDataLength,
          isValid: actualDataLength === declaredDataLength
        },
        gratingStatus: {
          lowerGrating: {
            code: lowerGrating,
            text: this.statusMaps.gratingStatus[lowerGrating] || `未知状态(${lowerGrating})`
          },
          upperGrating: {
            code: upperGrating,
            text: this.statusMaps.gratingStatus[upperGrating] || `未知状态(${upperGrating})`
          }
        },
        portCount: portCount,
        ports: ports,
        rawData: this._toHexString(buffer),
        isValid: true,
        warnings: []
      };
      
      // 7. 校验数据完整性      
      if (portDataLength % this.protocolConfig.portStructure.totalBytesPerPort !== 0) {
        const warningMsg = `数据长度不完整: Port口数据长度${portDataLength}不是每个Port口${this.protocolConfig.portStructure.totalBytesPerPort}字节的整数倍`;
        console.warn(warningMsg);
        result.warnings.push(warningMsg);
      }
      
      if (!result.header.isValid) {
        result.warnings.push(`数据长度不匹配: 声明${declaredDataLength}字节, 实际${actualDataLength}字节`);
      }
      
      if (ports.length === 0) {
        result.warnings.push("未解析到有效的Port口数据");
      }
      
      return result;
      
    } catch (error) {
      return {
        header: {
          fixed1: 0x00,
          fixed2: 0x00,
          declaredDataLength: 0,
          actualDataLength: 0,
          isValid: false
        },
        gratingStatus: {},
        portCount: 0,
        ports: [],
        rawData: typeof data === 'string' ? data.toUpperCase() : '',
        isValid: false,
        warnings: [],
        error: error.message
      };
    }
  }

  /**
   * 解析单个Port口的数据
   * @param {Uint8Array} buffer - 数据缓冲区
   * @param {number} offset - 起始偏移
   * @param {number} portNumber - Port口编号
   * @returns {Object} Port口数据
   */
  _parsePortData(buffer, offset, portNumber) {
    // 安全获取字节的函数
    const getByte = (index) => buffer.length > index ? buffer[index] : 0x00;
    const getInt16 = (index) => (getByte(index) << 8) | getByte(index + 1);
    
    // 解析状态变量（每个1字节）
    const readyStatus = getByte(offset);          // 字节0: 就绪状态
    const trayOkStatus = getByte(offset + 1);     // 字节1: TrayOk状态
    const onlineStatus = getByte(offset + 2);      // 字节2: 设备在线状态
    const trayPresentStatus = getByte(offset + 3); // 字节3: 有无tray盘状态
    const rollerStartStatus = getByte(offset + 4); // 字节4: Roller start状态
    const reserved = getByte(offset + 5);        // 字节5: 预留
    const manualOperation = getByte(offset + 6); // 字节6: 人工操作
    const traySize = getByte(offset + 7);        // 字节7: TraySize
    
    // 解析TrayId
    const trayIdStart = offset + 8; // 状态字节后开始
    const trayIdBuffer = new Uint8Array(this.protocolConfig.portStructure.trayIdBytesPerPort);
    for (let i = 0; i < this.protocolConfig.portStructure.trayIdBytesPerPort; i++) {
      trayIdBuffer[i] = getByte(trayIdStart + i);
    }
    const trayId = this._parseTrayId(trayIdBuffer);
    
    // 确定Port口位置（根据文档中的命名规则）
    let portPosition = '';
    if (portNumber <= 2) {
      portPosition = `下层左${portNumber}Port`;
    } else {
      portPosition = `上层左${portNumber - 2}Port`;
    }
    
    return {
      portNumber: portNumber,
      portPosition: portPosition,
      status: {
        readyStatus: {
          code: readyStatus,
          text: this.statusMaps.readyStatus[readyStatus] || `未知状态(${readyStatus})`
        },
        trayOkStatus: {
          code: trayOkStatus,
          text: this.statusMaps.trayOkStatus[trayOkStatus] || `未知状态(${trayOkStatus})`
        },
        onlineStatus: {
          code: onlineStatus,
          text: this.statusMaps.onlineStatus[onlineStatus] || `未知状态(${onlineStatus})`
        },
        trayPresentStatus: {
          code: trayPresentStatus,
          text: this.statusMaps.trayPresentStatus[trayPresentStatus] || `未知状态(${trayPresentStatus})`
        },
        rollerStartStatus: {
          code: rollerStartStatus,
          text: this.statusMaps.rollerStartStatus[rollerStartStatus] || `未知状态(${rollerStartStatus})`
        },
        reserved: {
          code: reserved,
          text: reserved === 0x00 ? '预留' : `未知预留值: 0x${reserved.toString(16).padStart(4, '0')}`
        },
        manualOperation: {
          code: manualOperation,
          text: this.statusMaps.manualOperation[manualOperation] || `未知状态(${manualOperation})`
        },
        traySize: {
          code: traySize,
          text: this.statusMaps.traySize[traySize] || `未知尺寸(${traySize})`
        }
      },
      trayId: trayId,
      rawData: this._toHexString(buffer.slice(offset, offset + this.protocolConfig.portStructure.totalBytesPerPort))
    };
  }

  /**
   * 解析TrayId
   * @param {Uint8Array} buffer - TrayId缓冲区（50字节）
   * @returns {string} 解析后的TrayId字符串
   */
  _parseTrayId(buffer) {
    let result = '';
    let hasValue = false;
    
    for (let i = 0; i < buffer.length; i++) {
      const byte = buffer[i];
      // 检查是否有实际值
      if (byte !== 0x00 && byte !== 0x20) {
        hasValue = true;
      }
      // 将字节转换为字符（ASCII）
      if (byte >= 0x20 && byte <= 0x7E) {
        result += String.fromCharCode(byte);
      } else if (byte === 0x00) {
        // 遇到0x00，转换为空格（根据业务要求）
        result += ' ';
      } else {
        // 非ASCII字符，用空格代替
        result += ' ';
      }
    }
    
    // 如果没有实际值，返回"无"
    if (!hasValue) {
      return "无";
    }
    
    // 根据文档说明：长度不足50字节的，向后补空格
    // 所以移除末尾的空格
    // 同时移除中间的空格，只保留有效的字符
    const trimmedResult = result.trimEnd().replace(/\s/g, '');
    
    // 如果移除空格后为空，返回"00"
    return trimmedResult || "00";
  }

  /**
   * 预处理数据
   * @param {*} data - 原始数据
   * @returns {Uint8Array} 处理后的Uint8Array
   */
  _preprocessData(data) {
    if (typeof data === 'string') {
      // 处理十六进制字符串
      const cleanHex = data.replace(/[^0-9A-Fa-f]/g, '');
      if (cleanHex.length === 0) throw new Error("空数据");
      if (cleanHex.length % 2 !== 0) throw new Error("十六进制字符串长度不正确");
      
      const buffer = new Uint8Array(cleanHex.length / 2);
      for (let i = 0; i < cleanHex.length; i += 2) {
        buffer[i / 2] = parseInt(cleanHex.substr(i, 2), 16);
      }
      return buffer;
      
    } else if (data instanceof Uint8Array) {
      return data;
      
    } else if (Array.isArray(data)) {
      return new Uint8Array(data);
      
    } else if (data instanceof ArrayBuffer) {
      return new Uint8Array(data);
      
    } else {
      throw new Error("不支持的数据格式，支持: 十六进制字符串、Uint8Array、Array、ArrayBuffer");
    }
  }

  /**
   * 转换为十六进制字符串
   * @param {Uint8Array} buffer - 缓冲区
   * @returns {string} 十六进制字符串
   */
  _toHexString(buffer) {
    let hex = '';
    for (let i = 0; i < buffer.length; i++) {
      hex += buffer[i].toString(16).padStart(2, '0').toUpperCase();
    }
    return hex;
  }

  /**
   * 解析AGV控制指令（根据文档中的AGV部分）
   * @param {*} data - AGV发送的控制指令
   * @returns {Object} 解析结果
   */
  parseAGVCommand(data) {
    try {
      const buffer = this._preprocessData(data);
      
      if (buffer.length < 13) { // AGV指令至少13字节
        throw new Error("AGV指令数据长度不足");
      }
      
      if (buffer[0] !== 0x05 || buffer[1] !== 0x06) {
        throw new Error("无效的协议头，应为0x05 0x06");
      }
      
      const dataLength = buffer[2];
      if (dataLength !== 0x63) { // 文档中AGV指令数据长度固定为99(0x63)
        console.warn(`AGV指令数据长度异常: 期望0x63, 实际0x${dataLength.toString(16)}`);
      }
      
      return {
        header: {
          fixed1: buffer[0],
          fixed2: buffer[1],
          dataLength: dataLength
        },
        command: {
          commandType: buffer[3], // 指令标识
          commandTypeText: buffer[3] === 0x01 ? '读指令' : 
                          buffer[3] === 0x02 ? '控制指令' : '未知指令',
          layer: buffer[4], // 上下层标识
          layerText: buffer[4] === 0x01 ? '下层' : 
                    buffer[4] === 0x02 ? '上层' : '未知',
          port1: buffer[5], // 第一个Port口
          port2: buffer[6], // 第二个Port口
          agvArrived: buffer[7], // AGV到位
          rollerAction: buffer[8], // Port滚动
          agvTrayOk: buffer[9], // AGV TrayOk
          agvLeave: buffer[10], // AGV离开
          traySize: buffer[11] // TraySize
        },
        trayId: this._parseTrayId(buffer.slice(12, 62)), // 第一个TrayId
        trayId2: buffer[6] !== 0x00 ? this._parseTrayId(buffer.slice(62, 112)) : '', // 第二个TrayId
        rawData: this._toHexString(buffer),
        isValid: true
      };
      
    } catch (error) {
      return {
        header: {},
        command: {},
        trayId: '',
        trayId2: '',
        rawData: typeof data === 'string' ? data.toUpperCase() : '',
        isValid: false,
        error: error.message
      };
    }
  }
}

// 导出类
export default AGVProtocolParser;

// 使用示例
/*
const parser = new AGVProtocolParser();

// 示例1: 解析PLC状态数据
const plcData = "050600E600010001000200010001000041424344202020..."; // 十六进制字符串
const result = parser.parseEQStatus(plcData);
console.log(result);

// 示例2: 解析AGV控制指令
const agvCommand = "050663020101000100020001010041424344...";
const commandResult = parser.parseAGVCommand(agvCommand);
console.log(commandResult);
*/