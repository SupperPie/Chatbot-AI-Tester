#!/usr/bin/env python3
"""
数据迁移脚本：将 data/test_cases.json 迁移到 PostgreSQL 数据库
"""
import json
import sys
import os
from datetime import datetime

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal, SCHEMA
from app.models.test_case import TestCase
from app.models.category import Category

def load_json_data(file_path: str) -> list:
    """加载 JSON 数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def clean_value(value):
    """清理值：处理 NaN, None, 空字符串等"""
    if value is None:
        return None
    if isinstance(value, float):
        import math
        if math.isnan(value):
            return None
    if isinstance(value, str):
        if value.lower() in ('nan', 'none', 'null', ''):
            return None
        return value.strip()
    return value

def migrate_test_cases(json_path: str, dry_run: bool = False):
    """迁移测试用例数据"""
    print(f"📂 加载数据: {json_path}")
    data = load_json_data(json_path)
    print(f"   共 {len(data)} 条记录")
    
    db = SessionLocal()
    
    try:
        # 确保 root 目录存在
        root = db.query(Category).filter(Category.id == 'root').first()
        if not root:
            print("⚠️  root 目录不存在，正在创建...")
            root = Category(
                id='root',
                name='root',
                parent_id=None,
                path='/root',
                level=1,
                sort_order=0
            )
            db.add(root)
            db.commit()
            print("✅ root 目录已创建")
        
        # 统计
        skipped = 0
        inserted = 0
        updated = 0
        errors = []
        
        for i, item in enumerate(data):
            try:
                # 清理数据
                case_id = clean_value(item.get('id'))
                
                # 跳过无效记录（没有 id 或 input）
                if not case_id:
                    skipped += 1
                    continue
                
                input_text = clean_value(item.get('input'))
                if not input_text:
                    skipped += 1
                    continue
                
                # 准备字段
                case_type = clean_value(item.get('type')) or 'single'
                expected_output = clean_value(item.get('expected_output')) or ''
                retrieval_context = clean_value(item.get('retrieval_context'))
                description = clean_value(item.get('description'))
                turn_index = clean_value(item.get('turn_index'))
                validation = clean_value(item.get('validation'))
                overall_criteria = clean_value(item.get('overall_criteria'))
                tags = item.get('tags', [])
                if not isinstance(tags, list):
                    tags = []
                
                # 检查是否已存在（用于去重的复合键：id + turn_index）
                query = db.query(TestCase).filter(TestCase.id == case_id)
                if turn_index is not None:
                    query = query.filter(TestCase.turn_index == turn_index)
                existing = query.first()
                
                if existing:
                    # 更新现有记录
                    existing.type = case_type
                    existing.input = input_text
                    existing.expected_output = expected_output
                    existing.retrieval_context = retrieval_context
                    existing.description = description
                    existing.validation = validation
                    existing.overall_criteria = overall_criteria
                    existing.tags = tags
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    # 创建新记录
                    # 对于多轮对话，需要生成唯一 ID
                    unique_id = case_id
                    if turn_index is not None and turn_index > 1:
                        unique_id = f"{case_id}_T{int(turn_index)}"
                    
                    test_case = TestCase(
                        id=unique_id,
                        type=case_type,
                        input=input_text,
                        expected_output=expected_output,
                        retrieval_context=retrieval_context,
                        description=description,
                        turn_index=turn_index,
                        validation=validation,
                        overall_criteria=overall_criteria,
                        tags=tags,
                        category_id='root',
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(test_case)
                    inserted += 1
                
                # 每 100 条提交一次
                if (i + 1) % 100 == 0:
                    if not dry_run:
                        db.commit()
                    print(f"   处理进度: {i + 1}/{len(data)}")
                    
            except Exception as e:
                errors.append(f"记录 {i}: {str(e)}")
                db.rollback()
        
        # 最终提交
        if not dry_run:
            db.commit()
        
        print(f"\n📊 迁移结果:")
        print(f"   ✅ 新增: {inserted} 条")
        print(f"   🔄 更新: {updated} 条")
        print(f"   ⏭️  跳过: {skipped} 条 (无效记录)")
        print(f"   ❌ 错误: {len(errors)} 条")
        
        if errors:
            print(f"\n❌ 错误详情:")
            for err in errors[:10]:  # 只显示前10个错误
                print(f"   {err}")
            if len(errors) > 10:
                print(f"   ... 还有 {len(errors) - 10} 个错误")
        
        if dry_run:
            print(f"\n⚠️  这是预演模式，未实际写入数据库")
        
        return inserted, updated, skipped, len(errors)
        
    finally:
        db.close()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='迁移 JSON 数据到 PostgreSQL')
    parser.add_argument('--dry-run', action='store_true', help='预演模式，不实际写入')
    parser.add_argument('--file', default='data/test_cases.json', help='JSON 文件路径')
    args = parser.parse_args()
    
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), args.file)
    
    if not os.path.exists(json_path):
        print(f"❌ 文件不存在: {json_path}")
        sys.exit(1)
    
    print("=" * 50)
    print("🚀 开始数据迁移")
    print("=" * 50)
    
    migrate_test_cases(json_path, dry_run=args.dry_run)
    
    print("=" * 50)
    print("✅ 迁移完成")
    print("=" * 50)

if __name__ == '__main__':
    main()
