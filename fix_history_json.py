#!/usr/bin/env python3
"""
History JSON 文件修复工具（强力版 v2）
用于修复因磁盘空间不足导致的 JSON 文件截断问题
"""

import json
import os
import re
import shutil
from datetime import datetime

# 目标文件路径
FILE_PATH = os.path.expanduser("~/chatbot-ai-tester/data/history.json")


def create_backup(file_path):
    """创建备份文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup.{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def find_last_complete_history_record(content):
    """
    找到最后一个完整的历史记录对象的结束位置
    历史记录结构: { "id": ..., "results": [...], "api_name": ..., "started_count": ... }
    完整记录以 "started_count": 数字 + } 结尾
    """
    # 匹配完整历史记录的结尾: "started_count": 数字 }
    pattern = r'"started_count"\s*:\s*\d+\s*\n?\s*\}'
    
    matches = list(re.finditer(pattern, content))
    
    if matches:
        last_match = matches[-1]
        return last_match.end()
    
    return None


def repair_json(content):
    """
    修复截断的 JSON 内容
    策略：找到最后一个完整的历史记录，删除之后的损坏记录
    """
    # 找到最后一个完整历史记录的位置
    last_complete_pos = find_last_complete_history_record(content)
    
    if last_complete_pos is None:
        print("[错误] 无法找到完整的历史记录结束位置")
        return None
    
    # 截断到最后一个完整历史记录
    truncated = content[:last_complete_pos]
    
    print(f"[分析] 最后一个完整记录结束位置: {last_complete_pos}")
    print(f"[分析] 原始文件大小: {len(content)} 字节")
    print(f"[分析] 截断后大小: {len(truncated)} 字节")
    print(f"[分析] 删除损坏数据: {len(content) - last_complete_pos} 字节")
    
    # 只需要闭合根数组
    repaired = truncated + "\n]"
    
    return repaired


def main():
    print("=" * 50)
    print("History JSON 文件修复工具（强力版 v2）")
    print("=" * 50)
    print()
    
    # 检查文件
    if not os.path.exists(FILE_PATH):
        print(f"[错误] 文件不存在: {FILE_PATH}")
        return 1
    
    print(f"[信息] 目标文件: {FILE_PATH}")
    print(f"[信息] 文件大小: {os.path.getsize(FILE_PATH)} 字节")
    
    # 读取文件
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 先测试是否真的损坏
    try:
        data = json.loads(content)
        print(f"[信息] 文件格式正常，无需修复")
        print(f"[信息] 包含 {len(data)} 条历史记录")
        return 0
    except json.JSONDecodeError as e:
        print(f"[警告] 检测到 JSON 错误: {e}")
    
    # 创建备份
    backup_path = create_backup(FILE_PATH)
    print(f"[备份] 已创建备份: {backup_path}")
    
    # 执行修复
    print("[修复] 开始修复...")
    repaired = repair_json(content)
    
    if repaired is None:
        print("[错误] 修复失败")
        return 1
    
    # 验证修复结果
    try:
        data = json.loads(repaired)
        print(f"[成功] JSON 验证通过")
        print(f"[成功] 保留历史记录: {len(data)} 条")
        
        # 显示保留的记录概要
        print()
        print("[保留的历史记录]:")
        for i, record in enumerate(data):
            record_id = record.get('id', 'unknown')
            api_name = record.get('api_name', 'unknown')
            status = record.get('status', 'unknown')
            print(f"  {i+1}. ID={record_id}, API={api_name}, Status={status}")
        
        # 写入修复后的文件
        with open(FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(repaired)
        
        print()
        print("=" * 50)
        print("修复完成！")
        print("=" * 50)
        return 0
        
    except json.JSONDecodeError as e:
        print(f"[错误] 修复后验证失败: {e}")
        print("[提示] 请手动检查文件或从备份恢复")
        return 1


if __name__ == "__main__":
    exit(main())
