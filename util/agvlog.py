import os
import subprocess

agv_log_dir = os.path.join(os.path.dirname(__file__), 'data','agvlog')
if not os.path.exists(agv_log_dir):
    os.makedirs(agv_log_dir)

def parse_agv_log(log_filename):
    """
    使用 parsezlib_2_7_8.exe 工具解析 AGV 日志文件
    
    Args:
        log_filename: AGV 日志文件名
    
    Returns:
        tuple: 生成的 txt 文件路径和AGV编号
    """
    if not log_filename.startswith("AGV_"):
        raise ValueError(f"AGV 日志文件名必须以 AGV_ 开头: {log_filename}")
    carid = log_filename.split('_CASTOR_')[1]
    
    # 先检查当前目录
    log_file_path = os.path.join(os.path.dirname(__file__), log_filename)
    if not os.path.exists(log_file_path):
        # 再检查 data/agvlog 目录
        log_file_path = os.path.join(agv_log_dir, log_filename)
        if not os.path.exists(log_file_path):
            raise FileNotFoundError(f"AGV 日志文件不存在: {log_file_path}")
    
    # 获取文件所在目录
    log_dir = os.path.dirname(log_file_path)
    log_filename = os.path.basename(log_file_path)
    
    # 构建 parsezlib 工具路径
    parsezlib_exe = os.path.join(os.path.dirname(__file__), 'tool', 'parsezlib_2_7_8.exe')
    
    if not os.path.exists(parsezlib_exe):
        raise FileNotFoundError(f"parsezlib 工具不存在: {parsezlib_exe}")
    
    # 生成的 txt 文件名格式: {编号}_{原文件名}_CASTOR.txt
    # 从原文件名提取编号，例如 AGV_2026_04_24_15_15_12_CASTOR_1032 -> 1032
    parts = log_filename.split('_')
    if len(parts) > 0:
        suffix = parts[-1]
        if suffix.isdigit():
            txt_filename = f"{suffix}_{'_'.join(parts[:-1])}.txt"
            txt_file_path = os.path.join(log_dir, txt_filename)
            if os.path.exists(txt_file_path):
                print(f"AGV日志文件 {log_filename} 已解析，直接返回 txt 文件: {txt_file_path}")
                return txt_file_path, carid
    
    # 执行解析命令
    try:
        result = subprocess.run(
            [parsezlib_exe, log_filename],
            cwd=log_dir,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"解析AGV日志文件 {log_filename} 输出: {result.stdout.strip()}")
        
        # 生成的 txt 文件名格式: {编号}_{原文件名}_CASTOR.txt
        # 从原文件名提取编号，例如 AGV_2026_04_24_15_15_12_CASTOR_1032 -> 1032
        parts = log_filename.split('_')
        if len(parts) > 0:
            suffix = parts[-1]
            if suffix.isdigit():
                txt_filename = f"{suffix}_{'_'.join(parts[:-1])}.txt"
                txt_file_path = os.path.join(log_dir, txt_filename)
                if os.path.exists(txt_file_path):
                    return txt_file_path, carid
        
        # 如果无法解析文件名格式，返回目录下最新的 txt 文件
        txt_files = [f for f in os.listdir(log_dir) if f.endswith('.txt')]
        if txt_files:
            txt_files.sort(key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True)
            return os.path.join(log_dir, txt_files[0])
        
        raise Exception("解析成功但未找到生成的 txt 文件")
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"解析失败: {e.stderr.strip()}")
    except Exception as e:
        raise Exception(f"解析过程出错: {str(e)}")


def find_str(log_file_path, search_pattern):
    """
    高效查找日志文件中包含指定字符串 的所有行
    
    Args:
        log_file_path: 日志文件路径
    
    Returns:
        list: 包含匹配行的列表，每个元素为 (行号, 行内容)
    """
    if not os.path.exists(log_file_path):
        raise FileNotFoundError(f"日志文件不存在: {log_file_path}")
    
    matching_lines = []
    
    # 使用生成器逐行读取，避免一次性加载整个文件到内存
    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line_number, line in enumerate(f, 1):
            if search_pattern in line:
                matching_lines.append((line_number, line.strip()))
    
    return matching_lines


def parse_pio_log_line(log_line):
    """
    解析AGV PIO检查日志行
    
    Args:
        log_line: 日志行字符串，格式如：[2026-04-24 15:19:00][60984][NOTIC][ROL]agv_check_pio_input result 1 pio_value 8d
    
    Returns:
        dict: 包含解析结果的字典，包括：
            - time: 时间字符串
            - line_number: 日志轮转行数
            - pio_result: 得到的pio值
            - pio_value: 需要的pio值
    """
    import re
    
    # 匹配日志行格式
    pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\[(\d+)\].*?agv_check_pio_input result (\d+) pio_value (\w+)'
    match = re.match(pattern, log_line)
    
    if not match:
        raise ValueError(f"无效的日志行格式: {log_line}")
    
    return {
        'time': match.group(1),
        'line_number': int(match.group(2)),
        'pio_result': int(match.group(3)),
        'pio_value': match.group(4)
    }


def merge_pio_logs(log_lines):
    """
    合并result和pio_value相同的日志行
    
    Args:
        log_lines: 日志行列表，每个元素为 (行号, 行内容)
    
    Returns:
        list: 合并后的结果列表，每个元素为：
            {
                'start_time': 开始时间,
                'end_time': 结束时间,
                'start_line': 开始行号,
                'end_line': 结束行号,
                'pio_result': 得到的pio值（十进制）,
                'pio_result_bin': 得到的pio值（二进制）,
                'pio_value': 需要的pio值（16进制）,
                'pio_value_bin': 需要的pio值（二进制）,
                'count': 合并的行数
            }
    """
    if not log_lines:
        return []
    
    # 先解析所有日志行
    parsed_logs = []
    for line_num, line in log_lines:
        try:
            parsed = parse_pio_log_line(line)
            parsed_logs.append(parsed)
        except ValueError:
            continue
    
    if not parsed_logs:
        return []
    
    # 按时间排序
    parsed_logs.sort(key=lambda x: x['time'])
    
    # 合并相同result和pio_value的记录
    merged = []
    current_group = None
    
    for log in parsed_logs:
        key = (log['pio_result'], log['pio_value'])
        
        if not current_group:
            # 开始新组
            # 将16进制转换为二进制
            try:
                pio_value_bin = bin(int(log['pio_value'], 16))[2:].zfill(8)  # 8位二进制
            except ValueError:
                pio_value_bin = log['pio_value']
            
            # 将得到的pio值转换为二进制
            pio_result_bin = bin(log['pio_result'])[2:].zfill(8)  # 8位二进制
                
            current_group = {
                'start_time': log['time'],
                'end_time': log['time'],
                'start_line': log['line_number'],
                'end_line': log['line_number'],
                'pio_result': log['pio_result'],
                'pio_result_bin': pio_result_bin,
                'pio_value': log['pio_value'],
                'pio_value_bin': pio_value_bin,
                'count': 1
            }
        else:
            current_key = (current_group['pio_result'], current_group['pio_value'])
            if current_key == key:
                # 同一组，更新结束时间和行数
                current_group['end_time'] = log['time']
                current_group['end_line'] = log['line_number']
                current_group['count'] += 1
            else:
                # 不同组，保存当前组并开始新组
                merged.append(current_group)
                
                # 将16进制转换为二进制
                try:
                    pio_value_bin = bin(int(log['pio_value'], 16))[2:].zfill(8)  # 8位二进制
                except ValueError:
                    pio_value_bin = log['pio_value']
                
                # 将得到的pio值转换为二进制
                pio_result_bin = bin(log['pio_result'])[2:].zfill(8)  # 8位二进制
                    
                current_group = {
                    'start_time': log['time'],
                    'end_time': log['time'],
                    'start_line': log['line_number'],
                    'end_line': log['line_number'],
                    'pio_result': log['pio_result'],
                    'pio_result_bin': pio_result_bin,
                    'pio_value': log['pio_value'],
                    'pio_value_bin': pio_value_bin,
                    'count': 1
                }
    
    # 保存最后一组
    if current_group:
        merged.append(current_group)
    
    return merged



if __name__ == "__main__":

    try:
        log, carid = parse_agv_log("AGV_2026_04_24_13_01_15_CASTOR_1032")
        print(f"AGV ID: {carid}")
        
        # 从文件中查找并解析日志行
        lines = find_str(log, "agv_check_pio_input")
        print(f"\n找到 {len(lines)} 行包含 agv_check_pio_input")
        
        # 测试合并功能
        merged_logs = merge_pio_logs(lines)
        print(f"\n合并后得到 {len(merged_logs)} 组")
        for i, group in enumerate(merged_logs, 1):
            print(f"\n组 {i}:")
            print(f"  时间范围: {group['start_time']} ~ {group['end_time']}")
            print(f"  日志行号范围: {group['start_line']} ~ {group['end_line']}")
            print(f"  得到的pio值(16进制): {group['pio_result']}")
            print(f"  得到的pio值(二进制): {group['pio_result_bin']}")
            print(f"  需要的pio值(16进制): {group['pio_value']}")
            print(f"  需要的pio值(二进制): {group['pio_value_bin']}")
            print(f"  合并行数: {group['count']}")
        # from pprint import pprint
        # pprint(merged_logs)
    except Exception as e:
        raise e

