from typing import List, Optional, Dict
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
import json
import math
import logging
from app.database import SessionLocal
# 必须先导入 Category，因为 TestCase 有外键引用
from app.models.category import Category
from app.models.test_case import TestCase

logger = logging.getLogger(__name__)


def _sanitize_record(r: dict) -> dict:
    """清洗一条记录，确保字段类型与 DB 列匹配。"""
    out = {}
    for k, v in r.items():
        # nan / 'nan' / 'None' → None
        if v is None:
            out[k] = None
        elif isinstance(v, float) and math.isnan(v):
            out[k] = None
        elif isinstance(v, str) and v.strip().lower() in ('nan', 'none'):
            out[k] = None
        else:
            out[k] = v

    # tags: JSONB 列，确保是 list（不能是字符串）
    tags = out.get('tags')
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            out['tags'] = parsed if isinstance(parsed, list) else [tags]
        except (json.JSONDecodeError, ValueError):
            out['tags'] = [tags] if tags.strip() else []

    # assertions: JSONB 列，确保是 list
    assertions = out.get('assertions')
    if isinstance(assertions, str):
        try:
            parsed = json.loads(assertions)
            out['assertions'] = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            out['assertions'] = []

    # overall_criteria / validation: Text 列，dict → JSON 字符串
    for field in ('overall_criteria', 'validation'):
        val = out.get(field)
        if isinstance(val, (dict, list)):
            out[field] = json.dumps(val, ensure_ascii=False)

    # priority: 仅允许 P0/P1/P2，其他值保持为空
    pr = out.get('priority')
    if isinstance(pr, str):
        pr = pr.strip().upper()
        out['priority'] = pr if pr in ('P0', 'P1', 'P2') else None
    elif pr is None:
        out['priority'] = None
    else:
        out['priority'] = str(pr).strip().upper() if str(pr).strip().upper() in ('P0', 'P1', 'P2') else None

    # module: 自由文本，仅做 trim
    md = out.get('module')
    if md is None:
        out['module'] = None
    else:
        s = str(md).strip()
        out['module'] = s if s else None

    return out


class TestCaseService:
    def __init__(self):
        self.db = SessionLocal()
    
    def get_all(self) -> List[TestCase]:
        """获取所有测试用例"""
        return self.db.query(TestCase).order_by(TestCase.id).all()
    
    def get_by_category(self, category_id: str) -> List[TestCase]:
        """获取指定目录下的测试用例"""
        return self.db.query(TestCase).filter(TestCase.category_id == category_id).all()
    
    def update_category(self, test_case_ids: List[str], category_id: str) -> int:
        """批量更新测试用例的目录"""
        count = self.db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).update(
            {TestCase.category_id: category_id},
            synchronize_session=False
        )
        self.db.commit()
        return count

    def update_priority_by_ids(self, test_case_ids: List[str], priority: Optional[str]) -> int:
        """按用例 ID 列表批量更新 priority（同 id 的所有 turn 一并更新）。"""
        if priority is not None:
            p = str(priority).strip().upper()
            if p not in ('P0', 'P1', 'P2'):
                raise ValueError("priority must be one of P0/P1/P2 or None")
            priority = p

        count = self.db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).update(
            {TestCase.priority: priority},
            synchronize_session=False
        )
        self.db.commit()
        return count

    def update_priority_by_filters(self, priority: Optional[str], category_id: Optional[str] = None, ids: Optional[List[str]] = None) -> int:
        """按过滤条件批量更新 priority。"""
        if priority is not None:
            p = str(priority).strip().upper()
            if p not in ('P0', 'P1', 'P2'):
                raise ValueError("priority must be one of P0/P1/P2 or None")
            priority = p

        q = self.db.query(TestCase)
        if category_id:
            q = q.filter(TestCase.category_id == category_id)
        if ids:
            q = q.filter(TestCase.id.in_(ids))

        count = q.update({TestCase.priority: priority}, synchronize_session=False)
        self.db.commit()
        return count

    def update_module_by_ids(self, test_case_ids: List[str], module: Optional[str]) -> int:
        """按用例 ID 列表批量更新 module（同 id 的所有 turn 一并更新）。"""
        if module is not None:
            module = str(module).strip() or None
        count = self.db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).update(
            {TestCase.module: module},
            synchronize_session=False
        )
        self.db.commit()
        return count

    def delete_by_ids(self, ids: List[str]) -> int:
        """按 ID 列表批量删除测试用例"""
        count = self.db.query(TestCase).filter(TestCase.id.in_(ids)).delete(synchronize_session=False)
        self.db.commit()
        return count

    def _bulk_upsert(self, records: List[Dict], batch_size: int = 500,
                     on_conflict: str = 'update') -> int:
        """批量写 DB：使用 PostgreSQL INSERT ... ON CONFLICT，一条 SQL 写一批。

        相比逐条 SELECT+INSERT/UPDATE（每条 2~3 次网络往返），4000 条导入
        从十几分钟缩短到几秒。

        Args:
            records: 待写入的记录列表（无需预先清洗）
            batch_size: 每条 SQL 携带的行数
            on_conflict: 'update' 冲突时更新已有行；'nothing' 冲突时跳过（只插新）
        Returns:
            实际发送到 DB 的记录数（含冲突跳过的行）
        """
        allowed_fields = {c.name for c in TestCase.__table__.columns}
        now = datetime.utcnow()

        # 预清洗 + 批内按 (id, turn_index) 去重（后出现的覆盖先出现的，
        # 与 ORM 逐条 upsert "最后一条生效" 的语义一致）
        dedup: Dict[tuple, Dict] = {}
        for r in records:
            if not r.get('id'):
                continue
            clean = _sanitize_record(r)
            ti = int(clean.get('turn_index') or 1)
            clean['turn_index'] = ti
            clean = {k: v for k, v in clean.items() if k in allowed_fields}
            clean.setdefault('created_at', now)
            clean.setdefault('updated_at', now)
            dedup[(clean['id'], ti)] = clean

        if not dedup:
            return 0

        rows = list(dedup.values())
        count = 0
        errors = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            stmt = pg_insert(TestCase).values(batch)
            if on_conflict == 'nothing':
                stmt = stmt.on_conflict_do_nothing(index_elements=['id', 'turn_index'])
            else:
                # 冲突时更新除主键、created_at 外的所有列（created_at 保留首次插入值）
                update_cols = {
                    c.name: getattr(stmt.excluded, c.name)
                    for c in TestCase.__table__.columns
                    if c.name not in ('id', 'turn_index', 'created_at')
                }
                update_cols['updated_at'] = now
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id', 'turn_index'],
                    set_=update_cols,
                )
            try:
                self.db.execute(stmt)
                count += len(batch)
            except Exception as e:
                # 批内可能混有脏数据：回滚后降级为逐条写，单条失败只跳过该条
                self.db.rollback()
                for row in batch:
                    try:
                        row_stmt = pg_insert(TestCase).values(row)
                        if on_conflict == 'nothing':
                            row_stmt = row_stmt.on_conflict_do_nothing(index_elements=['id', 'turn_index'])
                        else:
                            update_cols = {
                                c.name: getattr(row_stmt.excluded, c.name)
                                for c in TestCase.__table__.columns
                                if c.name not in ('id', 'turn_index', 'created_at')
                            }
                            update_cols['updated_at'] = now
                            row_stmt = row_stmt.on_conflict_do_update(
                                index_elements=['id', 'turn_index'],
                                set_=update_cols,
                            )
                        self.db.execute(row_stmt)
                        count += 1
                    except Exception as e2:
                        errors += 1
                        self.db.rollback()
                        logger.warning(f"[_bulk_upsert] skip record id={row.get('id')} turn={row.get('turn_index')}: {e2}")
                self.db.commit()

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"[_bulk_upsert] final commit failed: {e}")
            self.db.rollback()
        if errors:
            logger.warning(f"[_bulk_upsert] completed with {count} ok, {errors} errors")
        return count

    def insert_many(self, records: List[Dict]) -> int:
        """只插入新记录，已存在的 (id, turn_index) 跳过"""
        return self._bulk_upsert(records, on_conflict='nothing')

    def upsert_all(self, records: List[Dict]) -> int:
        """批量 upsert：更新已有、新增缺少（不自动删除其他记录）"""
        # 注意：此方法不会删除数据库中不在 records 里的记录
        # 如需删除，请显式调用 delete_by_ids()
        return self._bulk_upsert(records, on_conflict='update')

    def upsert_records(self, records: List[Dict]) -> int:
        """增量 upsert：只对给定的若干条记录做更新或插入。

        与 upsert_all 的区别：
        - 语义明确为"只保存这几条"，不做全量同步
        - 不含任何 ID 自动生成/重分配逻辑：id 仅作为 (id, turn_index) 定位条件
        """
        return self._bulk_upsert(records, on_conflict='update')

    def get_max_tc_id_num(self) -> int:
        """查询 DB 中最大的 TCxxxx 数字部分，用于生成新 ID 避免冲突"""
        # 取出所有 TC 开头的 id，提取数字部分取最大值
        # 使用 SQL 子查询在 DB 端做正则匹配，避免拉全表
        from sqlalchemy import text
        result = self.db.execute(
            text("SELECT MAX(CAST(SUBSTRING(id FROM 3) AS INTEGER)) FROM ai_chatbot_tester.test_cases WHERE id LIKE 'TC%'")
        ).scalar()
        return int(result) if result else 0

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
