#!/usr/bin/env python3
"""
完整数据迁移脚本：将所有 JSON 数据迁移到 PostgreSQL
"""
import json
import sys
import os
import uuid
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.database import SessionLocal, SCHEMA

def load_json(file_path: str):
    """加载 JSON 文件"""
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), file_path)
    if not os.path.exists(full_path):
        print(f"⚠️  文件不存在: {full_path}")
        return None
    with open(full_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def migrate_api_configs(db, dry_run=False):
    """迁移 API 配置"""
    print("\n📡 迁移 API 配置...")
    data = load_json('data/api_config.json')
    if not data:
        return 0
    
    inserted = 0
    for name, config in data.items():
        # 检查是否已存在 (name 是主键)
        result = db.execute(text(f"SELECT name FROM {SCHEMA}.api_configs WHERE name = :name"), {"name": name})
        if result.fetchone():
            continue
        
        if not dry_run:
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.api_configs (name, url, description, type)
                VALUES (:name, :url, :description, :type)
            """), {
                "name": name,
                "url": config.get("url", ""),
                "description": config.get("description", ""),
                "type": config.get("type", "")
            })
        inserted += 1
    
    if not dry_run:
        db.commit()
    print(f"   ✅ API 配置: {inserted} 条")
    return inserted

def migrate_blind_reviews(db, dry_run=False):
    """迁移盲测数据"""
    print("\n🔍 迁移盲测数据...")
    data = load_json('data/blind_reviews.json')
    if not data:
        return 0, 0
    
    reviews_inserted = 0
    items_inserted = 0
    
    for review in data:
        review_id = review.get('id', str(uuid.uuid4()))
        
        # 检查是否已存在
        result = db.execute(text(f"SELECT id FROM {SCHEMA}.blind_reviews WHERE id = :id"), {"id": review_id})
        if result.fetchone():
            continue
        
        created_at = review.get('created_at')
        if created_at:
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except:
                created_at = datetime.utcnow()
        else:
            created_at = datetime.utcnow()
        
        if not dry_run:
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.blind_reviews (id, name, created_at)
                VALUES (:id, :name, :created_at)
            """), {
                "id": review_id,
                "name": review.get('name', f'Review {created_at}'),
                "created_at": created_at
            })
        reviews_inserted += 1
        
        # 迁移盲测项目 (id 是自增列，不需要指定)
        for idx, item in enumerate(review.get('items', [])):
            if not dry_run:
                db.execute(text(f"""
                    INSERT INTO {SCHEMA}.blind_review_items (review_id, input, options, votes)
                    VALUES (:review_id, :input, :options, :votes)
                """), {
                    "review_id": review_id,
                    "input": item.get('input', ''),
                    "options": json.dumps(item.get('options', {})),
                    "votes": json.dumps(item.get('votes', {}))
                })
            items_inserted += 1
    
    if not dry_run:
        db.commit()
    print(f"   ✅ 盲测记录: {reviews_inserted} 条, 盲测项: {items_inserted} 条")
    return reviews_inserted, items_inserted

def migrate_history(db, dry_run=False):
    """迁移测试历史"""
    print("\n📊 迁移测试历史...")
    data = load_json('data/history.json')
    if not data:
        return 0, 0
    
    history_inserted = 0
    results_inserted = 0
    
    for record in data:
        history_id = record.get('id', str(uuid.uuid4()))
        
        # 检查是否已存在
        result = db.execute(text(f"SELECT id FROM {SCHEMA}.test_history WHERE id = :id"), {"id": history_id})
        if result.fetchone():
            continue
        
        timestamp = record.get('timestamp')
        if timestamp:
            try:
                timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            except:
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()
        
        if not dry_run:
            db.execute(text(f"""
                INSERT INTO {SCHEMA}.test_history (id, timestamp, total, passed, failed, status, api_name, created_at)
                VALUES (:id, :timestamp, :total, :passed, :failed, :status, :api_name, :created_at)
            """), {
                "id": history_id,
                "timestamp": timestamp,
                "total": record.get('total', 0),
                "passed": record.get('passed', 0),
                "failed": record.get('failed', 0),
                "status": record.get('status', 'completed'),
                "api_name": record.get('api_name'),
                "created_at": timestamp
            })
        history_inserted += 1
        
        # 迁移测试结果
        # 安全获取数值
        def safe_float(val):
            if val is None:
                return None
            try:
                return float(val)
            except:
                return None
        
        for res in record.get('results', []):
            # id 是自增列，不需要指定
            if not dry_run:
                db.execute(text(f"""
                    INSERT INTO {SCHEMA}.test_results 
                    (history_id, case_id, input, actual_output, expected_output, retrieval_context,
                     score, reason, faithfulness_score, faithfulness_reason, passed, thinking,
                     inform_base, raw, latency, ttft, created_at)
                    VALUES (:history_id, :case_id, :input, :actual_output, :expected_output, :retrieval_context,
                            :score, :reason, :faithfulness_score, :faithfulness_reason, :passed, :thinking,
                            :inform_base, :raw, :latency, :ttft, :created_at)
                """), {
                    "history_id": history_id,
                    "case_id": res.get('case_id'),
                    "input": res.get('input'),
                    "actual_output": res.get('actual_output'),
                    "expected_output": res.get('expected_output'),
                    "retrieval_context": res.get('retrieval_context'),
                    "score": safe_float(res.get('score')),
                    "reason": res.get('reason'),
                    "faithfulness_score": safe_float(res.get('faithfulness_score')),
                    "faithfulness_reason": res.get('faithfulness_reason'),
                    "passed": res.get('passed', False),
                    "thinking": res.get('thinking'),
                    "inform_base": res.get('inform_base'),
                    "raw": res.get('raw'),
                    "latency": safe_float(res.get('latency')),
                    "ttft": safe_float(res.get('ttft')),
                    "created_at": timestamp
                })
            results_inserted += 1
        
        # 每 10 条历史记录提交一次
        if history_inserted % 10 == 0 and not dry_run:
            db.commit()
            print(f"   处理进度: {history_inserted} 条历史记录...")
    
    if not dry_run:
        db.commit()
    print(f"   ✅ 测试历史: {history_inserted} 条, 测试结果: {results_inserted} 条")
    return history_inserted, results_inserted

def main():
    import argparse
    parser = argparse.ArgumentParser(description='迁移所有 JSON 数据到 PostgreSQL')
    parser.add_argument('--dry-run', action='store_true', help='预演模式')
    parser.add_argument('--only', choices=['api', 'blind', 'history', 'all'], default='all', help='只迁移指定类型')
    args = parser.parse_args()
    
    print("=" * 50)
    print("🚀 开始完整数据迁移")
    if args.dry_run:
        print("⚠️  预演模式 - 不会实际写入数据")
    print("=" * 50)
    
    db = SessionLocal()
    
    try:
        if args.only in ['all', 'api']:
            migrate_api_configs(db, args.dry_run)
        
        if args.only in ['all', 'blind']:
            migrate_blind_reviews(db, args.dry_run)
        
        if args.only in ['all', 'history']:
            migrate_history(db, args.dry_run)
        
        print("\n" + "=" * 50)
        print("✅ 迁移完成!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    main()
