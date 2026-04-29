#!/usr/bin/env python3
"""
数据迁移脚本：将 data/test_cases.json 迁移到 PostgreSQL 数据库
支持复合主键 (id, turn_index)，正确处理多轮对话和 ID 冲突。

规则 1：同 ID + 全 single + 不同 input → 第一条保留原 ID，其余生成新 TC 编号
规则 2：同 ID + 混合 single/multi_turn → 修正 turn=1 的 single 为 multi_turn，多余 single 生成新 ID
规则 3：多轮对话保持原 ID + turn_index，不加 _T{n} 后缀
"""
import json
import sys
import os
import math
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal, SCHEMA
from app.models.test_case import TestCase
from app.models.category import Category


def load_json_data(file_path: str) -> list:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        if value.strip().lower() in ('nan', 'none', 'null', ''):
            return None
        return value.strip()
    return value


def serialize_json_field(value):
    """将 dict/list 类型的字段序列化为 JSON 字符串，供 DB Text 列使用"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value
    return str(value)


def safe_int(value, default=1):
    """安全地将 turn_index 转为 int"""
    if value is None:
        return default
    try:
        v = float(value)
        if math.isnan(v):
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


def get_max_tc_num(db):
    """查询 DB 中当前最大的 TC 编号"""
    from sqlalchemy import text
    result = db.execute(text(f"""
        SELECT id FROM {SCHEMA}.test_cases WHERE id LIKE 'TC%' ORDER BY id DESC LIMIT 1
    """)).fetchone()
    if result:
        try:
            return int(result[0][2:])
        except (ValueError, IndexError):
            pass
    return 0


def preprocess_records(data: list):
    """
    预处理：按 ID 分组，标记每条记录的处理方式。
    返回处理后的记录列表，每条记录新增 '_action' 和 '_new_id' 字段。
    """
    # 先清洗所有记录的基本字段
    records = []
    for item in data:
        case_id = clean_value(item.get('id'))
        input_text = clean_value(item.get('input'))
        if not case_id or not input_text:
            continue
        records.append({
            '_original': item,
            'id': case_id,
            'input': input_text,
            'type': clean_value(item.get('type')) or 'single',
            'turn_index': safe_int(item.get('turn_index'), 1),
        })

    # 按 ID 分组
    groups = defaultdict(list)
    for r in records:
        groups[r['id']].append(r)

    # 收集所有原始 ID，用于新 ID 生成时避免冲突
    all_existing_ids = set(groups.keys())

    # 新 ID 计数器：从所有 TC 编号的最大值开始
    max_tc_num = 0
    for cid in all_existing_ids:
        if cid.startswith('TC'):
            try:
                num = int(cid[2:])
                max_tc_num = max(max_tc_num, num)
            except (ValueError, IndexError):
                pass

    def generate_new_id():
        nonlocal max_tc_num
        max_tc_num += 1
        new_id = f"TC{str(max_tc_num).zfill(4)}"
        while new_id in all_existing_ids:
            max_tc_num += 1
            new_id = f"TC{str(max_tc_num).zfill(4)}"
        all_existing_ids.add(new_id)
        return new_id

    # 按组处理
    processed = []
    for case_id, group in groups.items():
        singles = [r for r in group if r['type'] == 'single']
        multis = [r for r in group if r['type'] == 'multi_turn']

        if len(group) == 1:
            # 无冲突
            group[0]['_action'] = 'keep'
            group[0]['_new_id'] = case_id
            processed.append(group[0])

        elif multis:
            # 规则 2：有 multi_turn 记录
            has_turn_1_multi = any(r['turn_index'] == 1 for r in multis)

            if not has_turn_1_multi and singles:
                # 需要将一条 single 改为 multi_turn turn=1
                # 选择 turn_index=1 的 single（最可能是多轮对话的第一轮）
                converted = singles[0]
                converted['type'] = 'multi_turn'
                converted['turn_index'] = 1
                converted['_action'] = 'fix_type'
                converted['_new_id'] = case_id
                processed.append(converted)

                # 剩余 single 各自生成新 ID（规则 1）
                for s in singles[1:]:
                    s['_action'] = 'rename'
                    s['_new_id'] = generate_new_id()
                    processed.append(s)
            else:
                # multi_turn 已有 turn=1，所有 single 都需要新 ID
                for s in singles:
                    s['_action'] = 'rename'
                    s['_new_id'] = generate_new_id()
                    processed.append(s)

            # 规则 3：multi_turn 记录保持原 ID
            # 处理同一 turn_index 出现多次的情况（数据错误）
            seen_turns = set()
            for m in multis:
                if m['turn_index'] in seen_turns:
                    # 同 ID + 同 turn_index 的 multi_turn 重复，给新 ID
                    m['_action'] = 'rename'
                    m['_new_id'] = generate_new_id()
                    m['type'] = 'single'
                    m['turn_index'] = 1
                else:
                    seen_turns.add(m['turn_index'])
                    m['_action'] = 'keep'
                    m['_new_id'] = case_id
                processed.append(m)

        else:
            # 规则 1：全是 single，第一条保持原 ID，其余生成新 ID
            singles[0]['_action'] = 'keep'
            singles[0]['_new_id'] = case_id
            processed.append(singles[0])

            for s in singles[1:]:
                s['_action'] = 'rename'
                s['_new_id'] = generate_new_id()
                processed.append(s)

    return processed, max_tc_num


def migrate_test_cases(json_path: str, dry_run: bool = False):
    print(f"📂 加载数据: {json_path}")
    data = load_json_data(json_path)
    print(f"   共 {len(data)} 条原始记录")

    # 预处理
    processed, max_tc_num = preprocess_records(data)
    print(f"   预处理后 {len(processed)} 条有效记录")

    # 统计预处理结果
    action_counts = defaultdict(int)
    for r in processed:
        action_counts[r['_action']] += 1
    print(f"   keep={action_counts['keep']}, rename={action_counts['rename']}, fix_type={action_counts['fix_type']}")

    if dry_run:
        # 输出一些示例
        renamed = [r for r in processed if r['_action'] == 'rename']
        fixed = [r for r in processed if r['_action'] == 'fix_type']
        if renamed:
            print(f"\n   📝 重命名示例 (前 5 条):")
            for r in renamed[:5]:
                print(f"      {r['id']} → {r['_new_id']}  input={r['input'][:50]}")
        if fixed:
            print(f"\n   🔧 修正 type 示例:")
            for r in fixed[:5]:
                print(f"      {r['id']} turn={r['turn_index']} single→multi_turn")
        print(f"\n⚠️  预演模式，未写入数据库")
        return

    db = SessionLocal()
    try:
        # 确保 root 目录存在
        root = db.query(Category).filter(Category.id == 'root').first()
        if not root:
            root = Category(id='root', name='root', parent_id=None, path='/root', level=1, sort_order=0)
            db.add(root)
            db.commit()

        # 更新 DB 中的最大 TC 编号
        db_max = get_max_tc_num(db)
        if db_max > max_tc_num:
            max_tc_num = db_max

        inserted = 0
        updated = 0
        errors = []

        for i, record in enumerate(processed):
            try:
                item = record['_original']
                final_id = record['_new_id']
                final_turn = record['turn_index']
                final_type = record['type']

                # 准备字段
                expected_output = clean_value(item.get('expected_output')) or ''
                retrieval_context = clean_value(item.get('retrieval_context'))
                description = clean_value(item.get('description'))
                validation = serialize_json_field(clean_value(item.get('validation')))
                overall_criteria = serialize_json_field(clean_value(item.get('overall_criteria')))
                tags = item.get('tags', [])
                if not isinstance(tags, list):
                    tags = []

                # 查找是否已存在（复合主键）
                existing = db.query(TestCase).filter(
                    TestCase.id == final_id,
                    TestCase.turn_index == final_turn
                ).first()

                if existing:
                    existing.type = final_type
                    existing.input = record['input']
                    existing.expected_output = expected_output
                    existing.retrieval_context = retrieval_context
                    existing.description = description
                    existing.validation = validation
                    existing.overall_criteria = overall_criteria
                    existing.tags = tags
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    test_case = TestCase(
                        id=final_id,
                        turn_index=final_turn,
                        type=final_type,
                        input=record['input'],
                        expected_output=expected_output,
                        retrieval_context=retrieval_context,
                        description=description,
                        validation=validation,
                        overall_criteria=overall_criteria,
                        tags=tags,
                        category_id='root',
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(test_case)
                    inserted += 1

                # 每 100 条提交
                if (i + 1) % 100 == 0:
                    try:
                        db.commit()
                    except Exception as batch_err:
                        db.rollback()
                        errors.append(f"批次 {i-99}-{i} 提交失败: {str(batch_err)[:100]}，逐条重试...")
                        # 逐条重试该批次
                        for j in range(max(0, i - 99), i + 1):
                            try:
                                r = processed[j]
                                item2 = r['_original']
                                fid = r['_new_id']
                                fti = r['turn_index']
                                existing2 = db.query(TestCase).filter(
                                    TestCase.id == fid, TestCase.turn_index == fti
                                ).first()
                                if existing2:
                                    existing2.input = r['input']
                                    existing2.type = r['type']
                                    existing2.updated_at = datetime.utcnow()
                                else:
                                    db.add(TestCase(
                                        id=fid, turn_index=fti, type=r['type'],
                                        input=r['input'],
                                        expected_output=clean_value(item2.get('expected_output')) or '',
                                        retrieval_context=clean_value(item2.get('retrieval_context')),
                                        description=clean_value(item2.get('description')),
                                        validation=serialize_json_field(clean_value(item2.get('validation'))),
                                        overall_criteria=serialize_json_field(clean_value(item2.get('overall_criteria'))),
                                        tags=item2.get('tags', []) if isinstance(item2.get('tags'), list) else [],
                                        category_id='root',
                                        created_at=datetime.utcnow(), updated_at=datetime.utcnow()
                                    ))
                                db.commit()
                            except Exception:
                                db.rollback()
                    print(f"   进度: {i + 1}/{len(processed)}")

            except Exception as e:
                errors.append(f"记录 {i} ({record.get('_new_id', '?')}): {str(e)[:200]}")
                db.rollback()

        # 最终提交
        db.commit()

        print(f"\n📊 迁移结果:")
        print(f"   ✅ 新增: {inserted} 条")
        print(f"   🔄 更新: {updated} 条")
        print(f"   ❌ 错误: {len(errors)} 条")

        if errors:
            print(f"\n❌ 错误详情:")
            for err in errors[:10]:
                print(f"   {err}")

        # 验证
        from sqlalchemy import text
        total = db.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.test_cases")).scalar()
        multi = db.execute(text(f"SELECT COUNT(DISTINCT id) FROM {SCHEMA}.test_cases WHERE type = 'multi_turn'")).scalar()
        t_suffix = db.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.test_cases WHERE id LIKE '%\\_T%'")).scalar()
        print(f"\n📊 DB 验证:")
        print(f"   总记录数: {total}")
        print(f"   多轮对话用例数: {multi}")
        print(f"   _T 后缀记录数: {t_suffix} (应为 0)")

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
