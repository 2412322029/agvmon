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
        0x01: '接料已滚动',
        0x02: '送料已滚动'
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

    // ── 电梯（Lift · 纯轿厢式电梯/模式切换）AB66 协议 ─────────────────
    // 命令字最高位置 1 即电梯应答：0x01→0x81、0x02→0x82、0x03→0x83 …
    this.elevatorConfig = {
      stx1: 0xAB,
      stx2: 0x66,
      etx: 0x03,
      // 溢出字节数：STX(2) + BNK(1) + NOD(1) + LEN(1) + SUM(1) + ETX(1)
      overhead: 7,
    };
    this.elevatorCommands = {
      // AGV → 电梯
      0x01: { name: '查询电梯状态', dir: 'agv', dataLen: 3 },
      0x02: { name: 'AGV 登记(呼梯)', dir: 'agv', dataLen: 4 },
      0x03: { name: '电梯开门指令', dir: 'agv', dataLen: 3 },
      0x04: { name: '机器人状态/心跳', dir: 'agv', dataLen: 3 },
      0x05: { name: 'AGV 进料中', dir: 'agv', dataLen: 3 },
      0x06: { name: 'AGV 出料中', dir: 'agv', dataLen: 3 },
      0x08: { name: '电梯关门指令', dir: 'agv', dataLen: 3 },
      0x09: { name: '电梯模式切换', dir: 'agv', dataLen: 3 },
      // 电梯 → AGV
      0x81: { name: '查询电梯状态应答', dir: 'elevator', dataLen: 5 },
      0x82: { name: '呼梯应答', dir: 'elevator', dataLen: 3 },
      0x83: { name: '开门应答', dir: 'elevator', dataLen: 5 },
      0x84: { name: '心跳应答', dir: 'elevator', dataLen: 3 },
      0x85: { name: '进料应答', dir: 'elevator', dataLen: 3 },
      0x86: { name: '出料应答', dir: 'elevator', dataLen: 3 },
      0x88: { name: '关门应答', dir: 'elevator', dataLen: 5 },
      0x89: { name: '模式切换应答', dir: 'elevator', dataLen: 3 },
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
        const portData = this._parsePortData(buffer, portOffset, i + 1, portCount);
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
   * @param {number} portCount - Port口总数
   * @returns {Object} Port口数据
   */
  _parsePortData(buffer, offset, portNumber,portCount) {
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
    if (portNumber <= portCount / 2) {
      portPosition = `下左Port - ${portNumber}`;
    } else {
      portPosition = `上左Port - ${portNumber - portCount / 2}`;
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

  // ══════════════════════════════════════════════════════════════════
  //  电梯通信协议（纯轿厢式电梯 · 模式切换）—— AB66 报文
  //  帧结构：STX(AB 66) | BNK(1) | NOD(1) | LEN(1) | DATA(LEN) | SUM(1) | ETX(03)
  //    · BNK 组编号   ：1 号群为 0，2 号群为 1 …（无特殊说明填 00）
  //    · NOD 设备编号 ：1 号梯为 0x00，2 号梯为 0x01 …
  //    · SUM 校验和   ：SUM = ~(BNK + NOD + LEN + DATA) + 1，协议中为预留、默认不启用（示例填 00）
  //    · 一问一答，16 进制报文；命令字最高位置 1 表示电梯应答
  //  典型报文：
  //    查询状态  AB660000030100FF0003  →  AB6600000581000001200003（1 楼/AGV 模式/停梯）
  //    1 楼呼梯  AB66000004020000010003 →  AB660000038200010003
  //    前门开门  AB660000030300100003   →  AB6600000583000001200003
  //    进入 AGV 模式 AB660000030900010003 → AB660000038900010003
  // ══════════════════════════════════════════════════════════════════

  /**
   * 判断是否为电梯（Lift）AB66 报文
   * @param {string|Uint8Array|Array|ArrayBuffer} data
   * @returns {boolean}
   */
  isElevatorFrame(data) {
    return this._elevatorHex(data) !== null;
  }

  /**
   * 提取 AB66 报文的十六进制串（允许 'send: AB66 …' 之类前缀文本）
   * 非电梯报文、或 AB66 之后含非十六进制字符（例如中文错误提示）时返回 null
   * @returns {string|null}
   */
  _elevatorHex(data) {
    if (typeof data !== 'string') {
      if (data instanceof Uint8Array || Array.isArray(data) || data instanceof ArrayBuffer) {
        return this._toHexString(this._preprocessData(data));
      }
      return null;
    }
    const upper = data.trim().toUpperCase();
    const idx = upper.indexOf('AB66');
    if (idx < 0) return null;
    const hex = upper.slice(idx).replace(/[\s,;:|/\-_.]+/g, '');
    if (hex.length === 0 || hex.length % 2 !== 0) return null;
    if (!/^[0-9A-F]+$/.test(hex)) return null;
    return hex;
  }

  /** 数字 → 两位大写十六进制，非法值返回 '--' */
  _hex2(value) {
    return (typeof value === 'number' && value >= 0 && value <= 0xFF)
      ? value.toString(16).padStart(2, '0').toUpperCase()
      : '--';
  }

  /** 十六进制串 → Uint8Array */
  _hexToBytes(hex) {
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < hex.length; i += 2) {
      bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
    }
    return bytes;
  }

  /**
   * 解析电梯报文（request/response 中可能粘连多帧，逐帧扫描）
   * @param {*} data
   * @returns {{isValid:boolean, frames:Array<Object>, count:number, rawData:string,
   *            consumed:number, trailing:number, errors:string[], error?:string}}
   */
  parseElevatorStream(data) {
    const rawText = typeof data === 'string' ? data.trim() : '';
    const hex = this._elevatorHex(data);
    if (hex === null) {
      return {
        isValid: false, frames: [], count: 0, rawData: rawText,
        consumed: 0, trailing: 0, errors: [],
        error: rawText ? '非 AB66 电梯报文' : '空数据',
      };
    }

    const buf = this._hexToBytes(hex);
    const frames = [];
    const errors = [];
    let pos = 0;

    while (pos < buf.length) {
      const remain = buf.length - pos;
      if (remain < this.elevatorConfig.overhead) {
        errors.push(`偏移 ${pos} 起仅剩 ${remain} 字节，不足最短信文 ${this.elevatorConfig.overhead} 字节`);
        break;
      }
      if (buf[pos] !== this.elevatorConfig.stx1 || buf[pos + 1] !== this.elevatorConfig.stx2) {
        errors.push(`偏移 ${pos} 处报文头非 AB 66（实际 ${this._hex2(buf[pos])} ${this._hex2(buf[pos + 1])}）`);
        break;
      }
      const bnk = buf[pos + 2];
      const nod = buf[pos + 3];
      const len = buf[pos + 4];
      if (remain < len + this.elevatorConfig.overhead) {
        errors.push(`偏移 ${pos} 处报文不完整：LEN=${len}，需 ${len + this.elevatorConfig.overhead} 字节，实际剩余 ${remain} 字节`);
        break;
      }
      const dataBytes = Array.from(buf.slice(pos + 5, pos + 5 + len));
      const sum = buf[pos + 5 + len];
      const etx = buf[pos + 6 + len];
      const sumBase = (bnk + nod + len + dataBytes.reduce((s, v) => s + v, 0)) & 0xFF;
      const expectedSum = (0x100 - sumBase) & 0xFF;
      const rawHex = this._toHexString(buf.slice(pos, pos + len + this.elevatorConfig.overhead));

      const frame = this._buildElevatorFrame({
        bnk, nod, len, dataBytes, sum, etx, expectedSum, rawHex,
      });
      frames.push(frame);
      errors.push(...frame.warnings);
      pos += len + this.elevatorConfig.overhead;
    }

    return {
      isValid: frames.length > 0,
      frames,
      count: frames.length,
      rawData: hex,
      consumed: pos,
      trailing: buf.length - pos,
      errors,
      error: frames.length === 0 ? (errors[0] || '电梯报文解析失败') : undefined,
    };
  }

  /**
   * 解析单帧电梯报文（只取第 1 帧）
   * @param {*} data
   * @returns {Object} 帧对象，失败时返回 {isValid:false, error}
   */
  parseElevatorFrame(data) {
    const stream = this.parseElevatorStream(data);
    if (stream.isValid) {
      return { ...stream.frames[0], count: stream.count, rawData: stream.rawData };
    }
    return {
      isValid: false,
      command: {},
      fields: [],
      lines: [],
      warnings: [],
      rawData: stream.rawData,
      error: stream.error,
    };
  }

  /**
   * 生成供 UI 悬停提示使用的文本行（多帧时汇总）
   * @param {Object} stream parseElevatorStream 的结果
   * @returns {string[]}
   */
  elevatorTipLines(stream) {
    if (!stream || !stream.isValid || !stream.frames?.length) return [];
    const lines = [...stream.frames[0].lines];
    if (stream.count > 1) {
      lines.push(`报文含 ${stream.count} 帧：${stream.frames.map(f => f.command.name).join(' → ')}`);
    }
    for (const w of (stream.errors || []).slice(0, 2)) lines.push(`⚠ ${w}`);
    return lines;
  }

  /**
   * 合成电梯状态字节（状态类应答的第 5 个 DATA 字节）
   * @param {Object} o {mode, frontDoorOpen, rearDoorOpen, abnormal, up, down}
   *   mode: true/false 或 1/0 —— Bit5 电梯模式（1 AGV 模式 / 0 人工模式）
   * @returns {number} 0x00~0xFF
   */
  composeElevatorStatusByte(o = {}) {
    const bit = (v) => (v ? 1 : 0);
    return ((bit(o.mode) & 1) << 5)
      | ((bit(o.rearDoorOpen) & 1) << 4)
      | ((bit(o.frontDoorOpen) & 1) << 3)
      | ((bit(o.abnormal) & 1) << 2)
      | ((bit(o.down) & 1) << 1)
      | (bit(o.up) & 1);
  }

  /**
   * 按命令字与业务参数构造 DATA 字节（不含 STX/BNK/NOD/LEN/SUM/ETX）
   * @param {number} command 命令字
   * @param {Object} params  业务参数：
   *   id            ID 号（默认 0）
   *   floor         楼层（1~127，从 1 起）
   *   callMode      呼梯控制模式 0x00 超时关门 / 0x01 门常开
   *   rearDoor      呼梯前后门（true 后门 / false 前门）；开/关门指令为后门动作
   *   frontDoor     开/关门指令的前门动作
   *   robotStatus   机器人状态 Bit3~0（0 正常）
   *   flag          进料中 / 出料中标志（true = 1）
   *   agvMode       模式切换目标（true 进入 AGV 模式）
   *   success       应答结果（true 成功 / false 失败）
   *   mode, frontDoorOpen, rearDoorOpen, abnormal, up, down —— 状态类应答的状态位
   * @returns {{data:number[], warnings:string[]}}
   */
  buildElevatorData(command, params = {}) {
    const warnings = [];
    const int = (v, def = 0) => (typeof v === 'number' && Number.isFinite(v) ? Math.trunc(v) : def);
    const byte = (v, def = 0) => {
      const n = int(v, def);
      if (n < 0 || n > 0xFF) {
        warnings.push(`字节值 ${n} 超出 0x00~0xFF，已截断为 0x${this._hex2(n & 0xFF)}`);
        return n & 0xFF;
      }
      return n;
    };
    const id = byte(params.id, 0);
    const floorByte = () => {
      const f = int(params.floor, 1);
      if (f < 1 || f > 127) warnings.push(`楼层 ${f} 超出 1~127，已按低 7 位写入`);
      return f & 0x7F;
    };

    switch (command) {
      case 0x01:
        return { data: [0x01, id, 0xFF], warnings };

      case 0x02:
        return {
          data: [
            0x02, id,
            params.callMode === 0x01 ? 0x01 : 0x00,
            ((params.rearDoor ? 1 : 0) << 7) | floorByte(),
          ],
          warnings,
        };

      case 0x03:
      case 0x08:
        return {
          data: [
            command, id,
            ((params.rearDoor ? 1 : 0) << 5) | ((params.frontDoor ? 1 : 0) << 4),
          ],
          warnings,
        };

      case 0x04: {
        const st = byte(params.robotStatus, 0) & 0x0F;
        if (st !== 0) warnings.push(`机器人状态 0x${this._hex2(st)} 表示异常（0 为正常）`);
        return { data: [0x04, id, st], warnings };
      }

      case 0x05:
      case 0x06:
        return { data: [command, id, params.flag ? 0x01 : 0x00], warnings };

      case 0x09:
        return { data: [0x09, id, params.agvMode ? 0x01 : 0x00], warnings };

      case 0x81:
      case 0x83:
      case 0x88: {
        const statusByte = this.composeElevatorStatusByte(params);
        if (params.up && params.down) warnings.push('上行、下行同时置位，状态位疑似异常');
        return { data: [command, id, 0x00, floorByte(), statusByte], warnings };
      }

      case 0x82: {
        const ok = params.success === false ? 0x00 : 0x01;
        if (ok === 0x00) warnings.push('DATA[3] = 0x00：文档批注中同时表示“呼梯后超时关门模式”，注意与失败位区分');
        return { data: [0x82, id, ok], warnings };
      }

      case 0x84:
        return { data: [0x84, id, 0xFF], warnings };

      case 0x85:
      case 0x86:
      case 0x89:
        return { data: [command, id, params.success === false ? 0x00 : 0x01], warnings };

      default: {
        warnings.push(`命令字 0x${this._hex2(command)} 未在协议中定义，仅生成命令字 + ID 号`);
        return { data: [byte(command, 0), id], warnings };
      }
    }
  }

  /**
   * 构造完整电梯报文（无需下位机即可模拟一问一答）
   * @param {Object} opts
   *   command  命令字（0x01~0x09 / 0x81~0x89）
   *   bnk      组编号（默认 0 → 1 号群）
   *   nod      设备编号（默认 0 → 1 号梯）
   *   data     直接指定 DATA 字节（含命令字），优先于 params
   *   params   业务参数，见 buildElevatorData
   *   sum      'off'（默认，填 0x00，协议预留）| 'auto'（按 ~(BNK+NOD+LEN+DATA)+1 计算）| 具体数值
   * @returns {{hex:string, bytes:number[], dataBytes:number[], sum:number,
   *            sumExpected:number, warnings:string[]}}
   */
  buildElevatorFrame(opts = {}) {
    const { command = 0x01, bnk = 0, nod = 0, params = {}, sum = 'off' } = opts;
    let data;
    const warnings = [];

    if (Array.isArray(opts.data) && opts.data.length) {
      data = opts.data.map((v) => v & 0xFF);
    } else {
      const built = this.buildElevatorData(command & 0xFF, params);
      data = built.data;
      warnings.push(...built.warnings);
    }

    const b = (typeof bnk === 'number' ? bnk : 0) & 0xFF;
    const n = (typeof nod === 'number' ? nod : 0) & 0xFF;
    const bnkWarn = (v) => v < 0 || v > 0xFF;
    if (bnkWarn(bnk)) warnings.push('组编号超出 0x00~0xFF，已截断');
    if (bnkWarn(nod)) warnings.push('设备编号超出 0x00~0xFF，已截断');

    const len = data.length;
    const sumBase = (b + n + len + data.reduce((s, v) => s + v, 0)) & 0xFF;
    const sumExpected = (0x100 - sumBase) & 0xFF;
    const sumByte = sum === 'auto' ? sumExpected
      : (typeof sum === 'number' ? sum & 0xFF : 0x00);

    const bytes = [
      this.elevatorConfig.stx1, this.elevatorConfig.stx2,
      b, n, len,
      ...data,
      sumByte, this.elevatorConfig.etx,
    ];

    return {
      hex: this._toHexString(new Uint8Array(bytes)),
      bytes,
      dataBytes: data,
      sum: sumByte,
      sumExpected,
      warnings,
    };
  }

  /**
   * 解码状态类应答的第 5 个 DATA 字节（Bit5 模式 / Bit4 后门 / Bit3 前门 /
   * Bit2 电梯状态 / Bit1 下行 / Bit0 上行）
   * @param {number|undefined} b
   * @returns {Object}
   */
  _decodeElevatorStatusByte(b) {
    if (typeof b !== 'number') {
      return {
        code: undefined, hex: '--', mode: null, modeText: '--',
        frontDoorOpen: null, rearDoorOpen: null,
        elevatorStatus: null, statusText: '--',
        up: null, down: null, directionText: '--',
        text: '状态字节缺失', warnings: ['缺少第 5 个 DATA 字节（电梯状态位）'],
      };
    }
    const mode = (b >> 5) & 1;            // Bit5 电梯模式：1 AGV / 0 人工
    const rearDoorOpen = (b >> 4) & 1;    // Bit4 后门开门到位
    const frontDoorOpen = (b >> 3) & 1;   // Bit3 前门开门到位
    const elevatorStatus = (b >> 2) & 1;  // Bit2 电梯状态：0 正常 / 1 异常
    const down = (b >> 1) & 1;            // Bit1 下行
    const up = b & 1;                     // Bit0 上行

    const modeText = mode ? 'AGV 模式' : '人工模式(非 AGV)';
    const statusText = elevatorStatus ? '异常' : '正常';
    let directionText;
    if (up && down) directionText = '上行/下行同时置位';
    else if (up) directionText = '上行';
    else if (down) directionText = '下行';
    else directionText = '停梯';

    const warnings = [];
    if (up && down) warnings.push('上行、下行状态位同时为 1，疑似异常');

    return {
      code: b,
      hex: this._hex2(b),
      mode, modeText,
      rearDoorOpen, frontDoorOpen,
      elevatorStatus, statusText,
      up, down, directionText,
      reservedBits: `${(b >> 7) & 1}/${(b >> 6) & 1}`,
      text: `${modeText} | 前门开门到位 ${frontDoorOpen ? '✓' : '✗'} | 后门开门到位 ${rearDoorOpen ? '✓' : '✗'} | ${directionText} | 电梯状态 ${statusText}`,
      warnings,
    };
  }

  /**
   * 构建单帧解析结果（字段明细 + 悬停摘要行）
   * @param {Object} ctx {bnk, nod, len, dataBytes, sum, etx, expectedSum, rawHex}
   * @returns {Object}
   */
  _buildElevatorFrame({ bnk, nod, len, dataBytes, sum, etx, expectedSum, rawHex }) {
    const d = dataBytes;
    const get = (i) => (d.length > i ? d[i] : undefined);
    const hx = (v) => this._hex2(v);

    const cmdByte = get(0);
    const isResponse = typeof cmdByte === 'number' && cmdByte >= 0x80;
    const spec = this.elevatorCommands[cmdByte];
    const cmdName = spec ? spec.name
      : (typeof cmdByte === 'number' ? `未知命令字 0x${hx(cmdByte)}` : '命令字缺失');

    const lines = [];
    const warnings = [];
    const fields = [
      { field: 'STX', value: 'AB 66', note: '报文头' },
      { field: 'BNK', value: hx(bnk), note: `组编号 → ${bnk + 1} 号群` },
      { field: 'NOD', value: hx(nod), note: `设备编号 → ${nod + 1} 号梯` },
      { field: 'LEN', value: hx(len), note: `DATA 共 ${len} 字节` },
    ];

    let floor;          // 电梯所处楼层（从 1 起）
    let status = null;  // 第 5 个 DATA 字节（状态位）解码结果
    let result;         // 应答帧的执行结果：true 成功 / false 失败 / undefined 不适用

    switch (cmdByte) {
      // ── AGV → 电梯 ────────────────────────────────────────────────
      case 0x01: // 查询电梯状态
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: '查询电梯状态' });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: get(1) === 0 ? '默认 0x00' : `ID 0x${hx(get(1))}` });
        fields.push({ field: 'DATA[3]', value: hx(get(2)), note: get(2) === 0xFF ? '固定 0xFF' : '约定填 0xFF' });
        lines.push(`ID 0x${hx(get(1))} | 占位 0x${hx(get(2))}`);
        break;

      case 0x02: { // AGV 登记（呼梯）
        const modeByte = get(2);
        const floorByte = get(3);
        const callMode = modeByte === 0x00 ? '到达后超时自动关门'
          : modeByte === 0x01 ? '到达后，门保持常开'
            : `未知控制模式 0x${hx(modeByte)}`;
        const isRear = floorByte === undefined ? false : ((floorByte >> 7) & 1) === 1;
        floor = floorByte === undefined ? undefined : floorByte & 0x7F;
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: 'AGV 登记（呼梯）' });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: get(1) === 0 ? '默认 0x00' : `ID 0x${hx(get(1))}` });
        fields.push({ field: 'DATA[3] 控制模式', value: hx(modeByte), note: `00 ${'到达后超时自动关门'} / 01 到达后门常开` });
        fields.push({
          field: 'DATA[4] 门/楼层', value: hx(floorByte),
          note: `Bit7 前后门 = ${isRear ? '后门' : '前门'} | Bit6~0 登记楼层 = ${floor === undefined ? '--' : `${floor} 楼`}`,
        });
        lines.push(`${callMode} | ${isRear ? '后门' : '前门'} | 目标 ${floor === undefined ? '--' : `${floor} 楼`}`);
        break;
      }

      case 0x03: // 开门指令
      case 0x08: { // 关门指令
        const doorByte = get(2);
        const isOpen = cmdByte === 0x03;
        const label = isOpen ? '开门' : '关门';
        const rear = doorByte === undefined ? 0 : (doorByte >> 5) & 1;
        const front = doorByte === undefined ? 0 : (doorByte >> 4) & 1;
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: `电梯${label}指令` });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: get(1) === 0 ? '默认 0x00' : `ID 0x${hx(get(1))}` });
        fields.push({
          field: 'DATA[3] 门指令', value: hx(doorByte),
          note: `Bit5 后门${label} = ${rear} | Bit4 前门${label} = ${front} | Bit3~0 预留 = ${doorByte === undefined ? '--' : doorByte & 0x0F}`,
        });
        lines.push(`前门${label} ${front ? '✓' : '✗'}  后门${label} ${rear ? '✓' : '✗'}`);
        break;
      }

      case 0x04: { // 机器人状态及心跳
        const b = get(2);
        const code = b === undefined ? undefined : b & 0x0F;
        const text = code === undefined ? '--' : (code === 0 ? '正常' : `异常(0x${hx(code)})`);
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: '机器人状态 / 与电梯心跳' });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '默认 0x00' });
        fields.push({ field: 'DATA[3] 状态', value: hx(b), note: `Bit3~0 = ${code === undefined ? '--' : code}（0 正常 / 非 0 异常）` });
        lines.push(`机器人状态 ${text}`);
        break;
      }

      case 0x05: // AGV 进料中
      case 0x06: { // AGV 出料中
        const b = get(2);
        const flag = b === undefined ? undefined : b & 0x01;
        const label = cmdByte === 0x05 ? '进料中' : '出料中';
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: `AGV ${label}（液晶展示用，预留）` });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '默认 0x00' });
        fields.push({ field: 'DATA[3]', value: hx(b), note: `Bit0 = ${flag === undefined ? '--' : flag}（1 为${label}）` });
        lines.push(`${label}：${flag ? '是' : '否'}`);
        break;
      }

      case 0x09: { // 电梯模式切换
        const b = get(2);
        const agvMode = b === undefined ? undefined : b & 0x01;
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: '电梯模式切换' });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '默认 0x00' });
        fields.push({ field: 'DATA[3] 模式', value: hx(b), note: `Bit0 = ${agvMode === undefined ? '--' : agvMode}（1 进入 AGV 模式 / 0 退出为人工模式）` });
        lines.push(`切换 → ${agvMode ? 'AGV 模式' : '人工模式'}`);
        break;
      }

      // ── 电梯 → AGV ────────────────────────────────────────────────
      case 0x81: // 查询状态应答
      case 0x83: // 开门应答
      case 0x88: { // 关门应答
        const floorByte = get(3);
        const statusByte = get(4);
        floor = floorByte === undefined ? undefined : floorByte & 0x7F;
        status = this._decodeElevatorStatusByte(statusByte);
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: `${cmdName}（电梯状态返回）` });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '回显请求 ID' });
        fields.push({ field: 'DATA[3] 预留', value: hx(get(2)), note: get(2) === 0 ? '预留 0x00' : '预留字段' });
        fields.push({
          field: 'DATA[4] 楼层', value: hx(floorByte),
          note: `Bit7 预留 = ${floorByte === undefined ? '--' : (floorByte >> 7) & 1} | 电梯所处楼层 = ${floor === undefined ? '--' : `${floor} 楼（从 1 起）`}`,
        });
        fields.push({
          field: 'DATA[5] 状态位', value: hx(statusByte),
          note: `${status.text}（Bit7/Bit6 预留 = ${status.reservedBits}）`,
        });
        lines.push(`楼层 ${floor === undefined ? '--' : floor} 楼`);
        lines.push(status.text);
        warnings.push(...status.warnings);
        break;
      }

      case 0x82: { // 呼梯应答
        const b = get(2);
        const ok = b === undefined ? undefined : b & 0x01;
        const modeText = b === 0x00 ? '呼梯后超时关门模式（批注 00）'
          : b === 0x01 ? '呼梯后到达起始楼层门常开（批注 01）'
            : `预留值 0x${hx(b)}`;
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: '呼梯应答' });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '回显请求 ID' });
        fields.push({
          field: 'DATA[3] 结果', value: hx(b),
          note: `Bit0 = ${ok === undefined ? '--' : ok}（1 成功 / 0 失败）| 另有批注：${modeText}`,
        });
        lines.push(`呼梯结果：${ok ? '成功' : '失败'}`);
        lines.push(`控制模式：${modeText}`);
        result = ok === 1;
        break;
      }

      case 0x84: // 心跳应答
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: '心跳应答' });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '回显请求 ID' });
        fields.push({ field: 'DATA[3]', value: hx(get(2)), note: get(2) === 0xFF ? '固定 0xFF' : '约定填 0xFF' });
        lines.push('心跳正常');
        break;

      case 0x85: // 进料应答
      case 0x86: { // 出料应答
        const b = get(2);
        const ok = b === undefined ? undefined : b & 0x01;
        const label = cmdByte === 0x85 ? '进料' : '出料';
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: `${label}应答` });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '回显请求 ID' });
        fields.push({ field: 'DATA[3] 结果', value: hx(b), note: `Bit0 = ${ok === undefined ? '--' : ok}（1 成功 / 0 失败）` });
        lines.push(`${label}结果：${ok ? '成功' : '失败'}`);
        result = ok === 1;
        break;
      }

      case 0x89: { // 模式切换应答
        const b = get(2);
        const ok = b === undefined ? undefined : b & 0x01;
        fields.push({ field: 'DATA[1] 命令字', value: hx(get(0)), note: '模式切换应答' });
        fields.push({ field: 'DATA[2] ID 号', value: hx(get(1)), note: '回显请求 ID' });
        fields.push({ field: 'DATA[3] 结果', value: hx(b), note: `Bit0 = ${ok === undefined ? '--' : ok}（1 成功 / 0 失败）` });
        lines.push(`模式切换结果：${ok ? '成功' : '失败'}`);
        result = ok === 1;
        break;
      }

      default: {
        if (d.length === 0) {
          warnings.push('DATA 为空（LEN=0）');
          lines.push('无数据内容（LEN=0）');
        } else {
          d.forEach((v, i) => fields.push({
            field: `DATA[${i + 1}]`, value: hx(v), note: '未定义命令字，按原始字节展示',
          }));
          lines.push(`未定义命令字，DATA = ${this._toHexString(new Uint8Array(d))}`);
        }
        break;
      }
    }

    // DATA 长度与协议定义比对
    if (spec && len > spec.dataLen) {
      for (let i = spec.dataLen; i < len; i++) {
        fields.push({ field: `DATA[${i + 1}] 多余`, value: hx(d[i]), note: `超出协议定义长度 ${spec.dataLen} 字节` });
      }
      warnings.push(`DATA 长度 ${len} 超出协议定义 ${spec.dataLen} 字节`);
    } else if (spec && len < spec.dataLen) {
      warnings.push(`DATA 长度 ${len} 少于协议定义 ${spec.dataLen} 字节`);
    } else if (!spec) {
      warnings.push(`命令字${typeof cmdByte === 'number' ? ` 0x${hx(cmdByte)}` : ''}不在协议定义中`);
    }

    // SUM（协议预留、默认不启用）
    if (sum === 0x00) {
      fields.push({ field: 'SUM', value: hx(sum), note: '校验和（协议预留，默认不启用）' });
    } else if (sum === expectedSum) {
      fields.push({ field: 'SUM', value: hx(sum), note: `校验和正确（SUM = ~(BNK+NOD+LEN+DATA)+1 = ${hx(expectedSum)}）` });
    } else {
      fields.push({ field: 'SUM', value: hx(sum), note: `校验和不符，计算值 ${hx(expectedSum)}（SUM = ~(BNK+NOD+LEN+DATA)+1）` });
      warnings.push(`SUM 校验失败：报文 ${hx(sum)}，计算值 ${hx(expectedSum)}`);
    }

    // ETX
    if (etx === this.elevatorConfig.etx) {
      fields.push({ field: 'ETX', value: hx(etx), note: '报文尾' });
    } else {
      fields.push({ field: 'ETX', value: hx(etx), note: `报文尾异常，应为 ${this._hex2(this.elevatorConfig.etx)}` });
      warnings.push(`ETX 异常：${hx(etx)}，应为 ${this._hex2(this.elevatorConfig.etx)}`);
    }

    lines.unshift(
      `${isResponse ? '◀ 电梯应答' : '▶ AGV 下发'} ${cmdName}（0x${hx(cmdByte)}）| 梯#${nod + 1}${bnk ? ` 群#${bnk + 1}` : ''}`,
    );

    return {
      isValid: true,
      rawData: rawHex,
      bytes: [
        this.elevatorConfig.stx1, this.elevatorConfig.stx2,
        bnk, nod, len,
        ...d,
        sum, etx,
      ],
      bnk,
      nod,
      len,
      dataBytes: d,
      dataHex: this._toHexString(new Uint8Array(d)),
      sum,
      sumExpected: expectedSum,
      sumDisabled: sum === 0x00,
      etx,
      etxValid: etx === this.elevatorConfig.etx,
      direction: isResponse ? 'elevator' : 'agv',
      directionText: isResponse ? '电梯 → AGV' : 'AGV → 电梯',
      command: { code: cmdByte, hex: hx(cmdByte), name: cmdName, isResponse, known: !!spec },
      floor,
      floorText: floor === undefined ? '--' : `${floor} 楼`,
      status,
      result,
      fields,
      lines,
      warnings,
    };
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

// 示例3: 解析电梯（Lift）AB66 报文
const lift = parser.parseElevatorStream("AB6600000581000001200003");
console.log(lift.frames[0].command.name, lift.frames[0].floorText, lift.frames[0].status.text);
console.log(parser.elevatorTipLines(lift));
*/