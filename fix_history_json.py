#!/usr/bin/env python3
"""
修复因磁盘空间不足导致截断的 history.json 文件
用法: python3 fix_history_json.py [文件路径]
默认路径: ~/chatbot-ai-tester/data/history.json
"""

import json
import sys
import os
import shutil
from datetime import datetime


def get_default_path():
    """获取默认文件路径"""
    home = os.path.expanduser("~")
    return os.path.join(home, "chatbot-ai-tester", "data", "history.json")


def create_backup(file_path):
    """创建带时间戳的备份文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup.{timestamp}"
    shutil.copy2(file_path, backup_path)
    print(f"[备份] 已创建备份: {backup_path}")
    return backup_path


def find_last_complete_structure(content):
    """
    从后向前查找最后一个完整的 JSON 结构位置
    返回应该截断的位置和需要添加的闭合字符
    """
    brace_count = 0      # 花括号计数 {}
    bracket_count = 0    # 方括号计数 []
    in_string = False
    escape_next = False
    
    # 记录最后一个完整对象/数组的结束位置
    last_complete_pos = -1
    
    for i, char in enumerate(content):
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\':
            escape_next = True
            continue
            
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                # 一个对象刚完成
                if brace_count == 0 and bracket_count == 0:
                    last_complete_pos = i
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                # 数组元素完成
                if brace_count == 0 and bracket_count == 0:
                    last_complete_pos = i
    
    return last_complete_pos, brace_count, bracket_count


def smart_fix(content):
    """
    智能修复：截断到最后一个完整结构并正确闭合
    """
    # 去除末尾空白
    content = content.rstrip()
    
    # 找到最后一个完整结构的位置
    last_pos, brace_count, bracket_count = find_last_complete_structure(content)
    
    if last_pos < 0:
        # 没有找到完整结构，尝试简单截断到有效 JSON
        return simple_truncate(content)
    
    # 截断到最后一个完整结构
    truncated = content[:last_pos + 1]
    
    # 检查截断处后面是否有逗号
    remaining = content[last_pos + 1:].lstrip()
    if remaining.startswith(','):
        # 如果后面是逗号，保留逗号前的内容
        pass
    
    # 确定需要添加的闭合字符
    # 检查当前结构状态
    check_brace = 0
    check_bracket = 0
    in_str = False
    escape = False
    
    for char in truncated:
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"' and not escape:
            in_str = not in_str
            continue
        if not in_str:
            if char == '{':
                check_brace += 1
            elif char == '}':
                check_brace -= 1
            elif char == '[':
                check_bracket += 1
            elif char == ']':
                check_bracket -= 1
    
    # 添加必要的闭合字符
    fixed = truncated
    if check_brace > 0:
        fixed += '}' * check_brace
    if check_bracket > 0:
        fixed += ']' * check_bracket
    
    return fixed


def simple_truncate(content):
    """
    简单截断：逐个字符尝试，找到最长的有效 JSON 前缀
    """
    for i in range(len(content), 0, -1):
        try:
            test_content = content[:i]
            json.loads(test_content)
            return test_content
        except json.JSONDecodeError:
            continue
    return None


def validate_and_fix_array(content):
    """
    确保最终结果是有效的 JSON 数组
    """
    content = content.strip()
    
    # 如果不是以 [ 开头，可能需要包裹
    if not content.startswith('['):
        # 尝试找到数组开始
        start_idx = content.find('[')
        if start_idx >= 0:
            content = content[start_idx:]
    
    # 如果不是以 ] 结尾，添加它
    if not content.endswith(']'):
        # 去掉末尾可能的逗号
        content = content.rstrip().rstrip(',')
        content += '\n]'
    
    return content


def main():
    # 获取文件路径
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = get_default_path()
    
    print(f"[信息] 目标文件: {file_path}")
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"[错误] 文件不存在: {file_path}")
        sys.exit(1)
    
    # 读取文件
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"[错误] 读取文件失败: {e}")
        sys.exit(1)
    
    print(f"[信息] 原始文件大小: {len(original_content)} 字节")
    
    # 先尝试解析原文件
    try:
        original_data = json.loads(original_content)
        print(f"[信息] 文件格式正确，包含 {len(original_data)} 条记录")
        print("[信息] 无需修复")
        sys.exit(0)
    except json.JSONDecodeError as e:
        print(f"[警告] 检测到 JSON 错误: {e}")
    
    # 创建备份
    create_backup(file_path)
    
    # 执行修复
    print("[修复] 开始智能修复...")
    fixed_content = smart_fix(original_content)
    
    if fixed_content is None:
        print("[错误] 无法修复文件，损坏过于严重")
        sys.exit(1)
    
    # 确保是有效的数组格式
    fixed_content = validate_and_fix_array(fixed_content)
    
    # 验证修复结果
    try:
        fixed_data = json.loads(fixed_content)
        print(f"[成功] 修复验证通过，保留 {len(fixed_data)} 条记录")
    except json.JSONDecodeError as e:
        print(f"[错误] 修复后仍无效: {e}")
        print("[建议] 可能需要手动检查文件")
        sys.exit(1)
    
    # 写入修复后的文件
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        print(f"[完成] 修复后的文件已保存: {file_path}")
        print(f"[信息] 修复后文件大小: {len(fixed_content)} 字节")
    except Exception as e:
        print(f"[错误] 写入文件失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
