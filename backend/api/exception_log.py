import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path


class ExceptionLogDB:
    """
    AGV小车异常日志数据库操作类
    包含ID、时间、小车ID、问题描述、小车状态、备注字段
    """
    
    def __init__(self, db_path=None):
        """
        初始化数据库连接
        :param db_path: 数据库文件路径，默认保存在util/data目录下
        """
        if db_path is None:
            # 确保util/data目录存在
            data_dir = Path(__file__).parent.parent.parent / "util" / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "exception_log.db"
        else:
            self.db_path = Path(db_path)
        print(f"数据库路径: {self.db_path}")
        self.init_db()
    
    def init_db(self):
        """
        初始化数据库表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建异常日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exception_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agv_id TEXT NOT NULL,
                problem_description TEXT NOT NULL,
                agv_status TEXT,
                remarks TEXT
            )
        ''')
        
        # 创建索引以提高查询性能
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_agv_id ON exception_logs(agv_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON exception_logs(timestamp)')
        
        conn.commit()
        conn.close()
    
    def add_exception_log(self, agv_id, problem_description, agv_status=None, remarks=None):
        """
        添加异常日志
        :param agv_id: 小车ID
        :param problem_description: 问题描述
        :param agv_status: 小车状态
        :param remarks: 备注
        :return: 新插入记录的ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT INTO exception_logs (timestamp, agv_id, problem_description, agv_status, remarks)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, agv_id, problem_description, agv_status, remarks))
        
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return log_id
    
    def get_exception_log(self, log_id):
        """
        根据ID获取单条异常日志
        :param log_id: 日志ID
        :return: 异常日志记录或None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM exception_logs WHERE id = ?', (log_id,))
        record = cursor.fetchone()
        
        conn.close()
        
        if record:
            return {
                'id': record[0],
                'timestamp': record[1],
                'agv_id': record[2],
                'problem_description': record[3],
                'agv_status': record[4],
                'remarks': record[5]
            }
        return None
    
    def _execute_query(self, base_query, count_query, params=[], page=None, page_size=None):
        """
        执行查询的内部方法
        :param base_query: 基础查询语句
        :param count_query: 计数查询语句
        :param params: 查询参数
        :param page: 页码（从1开始）
        :param page_size: 每页记录数
        :return: 查询结果和分页信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 计算总数
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        # 构建最终查询语句
        final_query = base_query
        final_params = params[:]
        
        # 添加分页
        if page and page_size:
            offset = (page - 1) * page_size
            final_query += " LIMIT ? OFFSET ?"
            final_params.extend([page_size, offset])
        
        cursor.execute(final_query, final_params)
        records = cursor.fetchall()
        
        conn.close()
        
        result = []
        for record in records:
            result.append({
                'id': record[0],
                'timestamp': record[1],
                'agv_id': record[2],
                'problem_description': record[3],
                'agv_status': record[4],
                'remarks': record[5]
            })
        
        return {
            'data': result,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size if page_size else 1
        }
    
    def query_exception_logs(self, agv_id=None, keyword=None, start_date=None, end_date=None, agv_status=None, page=None, page_size=None):
        """
        统一查询异常日志接口（整合所有查询条件）
        :param agv_id: 小车ID过滤
        :param keyword: 关键词搜索（在问题描述、小车状态或备注中）
        :param start_date: 开始日期过滤
        :param end_date: 结束日期过滤
        :param agv_status: 小车状态过滤
        :param page: 页码（从1开始）
        :param page_size: 每页记录数
        :return: 查询结果列表和总记录数
        """
        # 构建动态查询语句
        conditions = []
        params = []
        
        if agv_id:
            conditions.append("agv_id = ?")
            params.append(agv_id)
        if keyword:
            conditions.append("(problem_description LIKE ? OR agv_status LIKE ? OR remarks LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)
        if agv_status:
            conditions.append("agv_status = ?")
            params.append(agv_status)
        
        # 构建基础查询
        base_query = "SELECT * FROM exception_logs"
        count_query = "SELECT COUNT(*) FROM exception_logs"
        
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
            base_query += where_clause
            count_query += where_clause
        
        base_query += " ORDER BY timestamp DESC"
        
        return self._execute_query(base_query, count_query, params, page, page_size)
    
    def update_exception_log(self, log_id, agv_id=None, problem_description=None, 
                           agv_status=None, remarks=None, timestamp=None):
        """
        更新异常日志
        :param log_id: 要更新的日志ID
        :param agv_id: 小车ID
        :param problem_description: 问题描述
        :param agv_status: 小车状态
        :param remarks: 备注
        :param timestamp: 时间戳
        :return: 更新是否成功
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 构建动态更新语句
        updates = []
        params = []
        
        if agv_id is not None:
            updates.append("agv_id = ?")
            params.append(agv_id)
        if problem_description is not None:
            updates.append("problem_description = ?")
            params.append(problem_description)
        if agv_status is not None:
            updates.append("agv_status = ?")
            params.append(agv_status)
        if remarks is not None:
            updates.append("remarks = ?")
            params.append(remarks)
        if timestamp is not None:
            updates.append("timestamp = ?")
            params.append(timestamp)
        
        if not updates:
            conn.close()
            return False
        
        params.append(log_id)
        update_sql = f"UPDATE exception_logs SET {', '.join(updates)} WHERE id = ?"
        
        cursor.execute(update_sql, params)
        success = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return success
    
    def delete_exception_log(self, log_id):
        """
        删除异常日志
        :param log_id: 要删除的日志ID
        :return: 删除是否成功
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM exception_logs WHERE id = ?', (log_id,))
        success = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return success
    
    def delete_exception_logs_by_agv(self, agv_id):
        """
        删除指定小车的所有异常日志
        :param agv_id: 小车ID
        :return: 删除的记录数量
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM exception_logs WHERE agv_id = ?', (agv_id,))
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def get_all_exception_logs(self, page=None, page_size=None):
        """
        获取所有异常日志（使用统一查询接口）
        :param page: 页码（从1开始）
        :param page_size: 每页记录数
        :return: 异常日志记录列表和总记录数
        """
        return self.query_exception_logs(page=page, page_size=page_size)
    
    def get_exception_logs_by_agv(self, agv_id, page=None, page_size=None):
        """
        根据小车ID获取异常日志（使用统一查询接口）
        :param agv_id: 小车ID
        :param page: 页码（从1开始）
        :param page_size: 每页记录数
        :return: 对应小车的异常日志记录列表和总记录数
        """
        return self.query_exception_logs(agv_id=agv_id, page=page, page_size=page_size)
    
    def search_exception_logs(self, keyword=None, agv_id=None, start_date=None, end_date=None, page=None, page_size=None):
        """
        搜索异常日志（保留旧接口，兼容性考虑，实际调用统一查询接口）
        :param keyword: 关键词搜索（在问题描述中）
        :param agv_id: 小车ID过滤
        :param start_date: 开始日期过滤
        :param end_date: 结束日期过滤
        :param page: 页码（从1开始）
        :param page_size: 每页记录数
        :return: 搜索结果列表和总记录数
        """
        # 调用统一查询接口
        return self.query_exception_logs(
            keyword=keyword, 
            agv_id=agv_id, 
            start_date=start_date, 
            end_date=end_date, 
            page=page, 
            page_size=page_size
        )
    
    def get_exception_logs_by_time_range(self, start_date, end_date, agv_id=None, page=None, page_size=None):
        """
        根据时间范围获取异常日志（使用统一查询接口）
        :param start_date: 开始时间（格式：'YYYY-MM-DD HH:MM:SS'）
        :param end_date: 结束时间（格式：'YYYY-MM-DD HH:MM:SS'）
        :param agv_id: 可选的小车ID过滤条件
        :param page: 页码（从1开始）
        :param page_size: 每页记录数
        :return: 在指定时间范围内的异常日志记录列表和总记录数
        """
        return self.query_exception_logs(
            agv_id=agv_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size
        )
    
    def export_to_csv(self, csv_file_path, agv_id=None, start_date=None, end_date=None):
        """
        导出异常日志到CSV文件
        :param csv_file_path: CSV文件路径
        :param agv_id: 可选的小车ID过滤条件
        :param start_date: 可选的开始日期过滤
        :param end_date: 可选的结束日期过滤
        :return: 成功与否
        """
        import csv
        
        try:
            # 获取符合条件的数据
            if start_date and end_date:
                if agv_id:
                    logs = self.get_exception_logs_by_time_range(start_date, end_date, agv_id)
                else:
                    logs = self.get_exception_logs_by_time_range(start_date, end_date)
                data = logs['data'] if isinstance(logs, dict) else logs
            elif agv_id:
                logs = self.get_exception_logs_by_agv(agv_id)
                data = logs['data'] if isinstance(logs, dict) else logs
            else:
                logs = self.get_all_exception_logs()
                data = logs['data'] if isinstance(logs, dict) else logs
            
            # 写入CSV文件
            with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'timestamp', 'agv_id', 'problem_description', 'agv_status', 'remarks']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for log in data:
                    writer.writerow(log)
            
            return True
        except Exception as e:
            print(f"导出CSV失败: {str(e)}")
            return False
    
    def import_from_csv(self, csv_file_path):
        """
        从CSV文件导入异常日志
        :param csv_file_path: CSV文件路径
        :return: 成功导入的记录数
        """
        import csv
        
        try:
            imported_count = 0
            with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    # 添加异常日志
                    self.add_exception_log(
                        agv_id=row.get('agv_id', ''),
                        problem_description=row.get('problem_description', ''),
                        agv_status=row.get('agv_status'),
                        remarks=row.get('remarks')
                    )
                    imported_count += 1
            
            return imported_count
        except Exception as e:
            print(f"导入CSV失败: {str(e)}")
            return 0


# 使用示例
if __name__ == "__main__":
    # 创建数据库实例
    db = ExceptionLogDB()
    
    # 添加测试数据
    log_id = db.add_exception_log(
        agv_id="AGV001",
        problem_description="电池电量过低",
        agv_status="停止运行",
        remarks="需要立即充电"
    )
    
    print(f"添加日志ID: {log_id}")
    
    # 查询刚添加的日志
    log = db.get_exception_log(log_id)
    print(f"查询结果: {log}")
    
    # 查询所有日志（带翻页）
    all_logs = db.get_all_exception_logs(page=1, page_size=10)
    print(f"所有日志: {all_logs}")
    
    # 更新日志
    update_success = db.update_exception_log(
        log_id=log_id,
        agv_status="正在充电"
    )
    print(f"更新结果: {update_success}")
    
    # 再次查询确认更新
    updated_log = db.get_exception_log(log_id)
    print(f"更新后的日志: {updated_log}")
    
    # 按小车ID查询（带翻页）
    agv_logs = db.get_exception_logs_by_agv("AGV001", page=1, page_size=10)
    print(f"AGV001的日志: {agv_logs}")
    
    # 搜索日志（带翻页）
    search_results = db.query_exception_logs(keyword="充电", page=1, page_size=10)
    print(f"搜索结果: {search_results}")
    
    # 统一查询测试
    unified_results = db.query_exception_logs(keyword="充电", agv_status="正在充电", page=1, page_size=10)
    print(f"统一查询结果: {unified_results}")
    
    # 测试时间范围查询（带翻页）
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    past_time = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    
    time_range_results = db.get_exception_logs_by_time_range(past_time, current_time, page=1, page_size=10)
    print(f"时间范围查询结果: {len(time_range_results['data'])} 条记录")
    
    # 添加更多测试数据以展示时间范围查询效果
    log_id2 = db.add_exception_log(
        agv_id="AGV002",
        problem_description="路径阻塞",
        agv_status="等待中",
        remarks="前方有障碍物"
    )
    time.sleep(1)  # 确保时间戳不同
    
    log_id3 = db.add_exception_log(
        agv_id="AGV001",
        problem_description="导航系统故障",
        agv_status="停止运行",
        remarks="重新启动导航系统"
    )
    
    # 测试导出功能
    export_success = db.export_to_csv("./test_export.csv")
    print(f"导出结果: {export_success}")
    
    # 测试导入功能
    imported_count = db.import_from_csv("./test_export.csv")
    print(f"导入记录数: {imported_count}")
    
    # 再次查询时间范围内的记录
    time_range_results = db.get_exception_logs_by_time_range(past_time, current_time, page=1, page_size=10)
    print(f"更新后时间范围查询结果: {len(time_range_results['data'])} 条记录")
    
    # 按小车ID和时间范围查询（带翻页）
    agv_time_range_results = db.get_exception_logs_by_time_range(past_time, current_time, agv_id="AGV001", page=1, page_size=10)
    print(f"AGV001在时间范围内的异常记录: {len(agv_time_range_results['data'])} 条记录")