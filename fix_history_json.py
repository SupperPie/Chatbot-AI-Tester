#!/usr/bin/env python3
"""
History JSON 文件修复工具（强力版）
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


def find_last_complete_object(content):
    """
    找到最后一个完整的 JSON 对象结束位置
    针对 results 数组中的对象被截断的情况
    """
    # 找所有 "ttft": 数字 后跟 } 的位置（这是每个 result 对象的结尾）
    # 匹配模式：完整的对象结尾标志
    pattern = r'"ttft"\s*:\s*[\d.]+\s*\n?\s*\}'
    
    matches = list(re.finditer(pattern, content))
    
    if matches:
        # 返回最后一个完整对象的结束位置
        last_match = matches[-1]
        return last_match.end()
    
    return None


def repair_json(content):
    """
    修复截断的 JSON 内容
    """
    # 找到最后一个完整对象的位置
    last_complete_pos = find_last_complete_object(content)
    
    if last_complete_pos is None:
        print("[错误] 无法找到完整的对象结束位置")
        return None
    
    # 截断到最后一个完整对象
    truncated = content[:last_complete_pos]
    
    # 分析需要闭合的结构
    # 计算未闭合的括号
    open_braces = truncated.count('{') - truncated.count('}')
    open_brackets = truncated.count('[') - truncated.count(']')
    
    print(f"[分析] 截断后位置: {last_complete_pos}")
    print(f"[分析] 需要闭合的 '{{}}': {open_braces} 个")
    print(f"[分析] 需要闭合的 '[]': {open_brackets} 个")
    
    # 构建闭合结构
    # 根据历史记录结构: [ { "results": [ {...}, {...} ], ... }, ... ]
    # 通常需要: ] (关闭 results) + } (关闭当前记录对象) + ] (关闭根数组)
    
    closing = ""
    closing += "\n" + " " * 12 + "]"  # 关闭 results 数组
    closing += ","
    closing += '\n        "api_name": "RECOVERED",'
    closing += '\n        "started_count": 0'
    closing += "\n    }"  # 关闭当前历史记录对象
    closing += "\n]"  # 关闭根数组
    
    repaired = truncated + closing
    
    return repaired


def main():
    print("=" * 50)
    print("History JSON 文件修复工具（强力版）")
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
        json.loads(content)
        print("[信息] 文件格式正常，无需修复")
        return 0
    except json.JSONDecodeError as e:
        print(f"[警告] 检测到 JSON 错误: {e}")
    
    # 创建备份
    backup_path = create_backup(FILE_PATH)
    print(f"[备份] 已创建备份: {backup_path}")
    
    # 执行修复
    print("[修复] 开始强力修复...")
    repaired = repair_json(content)
    
    if repaired is None:
        print("[错误] 修复失败")
        return 1
    
    # 验证修复结果
    try:
        data = json.loads(repaired)
        print(f"[成功] JSON 验证通过")
        print(f"[成功] 保留历史记录: {len(data)} 条")
        
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
