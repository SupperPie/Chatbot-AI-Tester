from typing import List, Dict, Optional
from datetime import datetime
from app.database import SessionLocal
import app.models  # noqa: F401 - ensure all models loaded for relationship resolution
from app.models.test_history import TestHistory, TestResult


class HistoryService:
    def __init__(self):
        self.db = SessionLocal()

    def get_all(self, include_results: bool = True) -> List[Dict]:
        """获取所有 history 记录，按时间倒序
        
        Args:
            include_results: 是否包含 results 详情，False 时只返回摘要（更快）
        """
        entries = self.db.query(TestHistory).order_by(TestHistory.timestamp.desc()).all()
        result = []
        for entry in entries:
            result.append(self._entry_to_dict(entry, include_results=include_results))
        return result

    def get_by_id(self, history_id: str) -> Optional[Dict]:
        """获取单条 history（含 results）"""
        entry = self.db.query(TestHistory).filter(TestHistory.id == history_id).first()
        if entry:
            return self._entry_to_dict(entry)
        return None

    def save(self, results: List[Dict], api_name: str = "Unknown", report_name: str = None) -> str:
        """保存一次测试执行结果到 DB"""
        now = datetime.utcnow()
        history_id = now.strftime("%Y%m%d%H%M%S")
        # 同秒内可能与其他报告（如 JobManager 生成的）主键冲突，冲突时加后缀重试
        for attempt in range(5):
            existing = self.db.query(TestHistory).filter(TestHistory.id == history_id).first()
            if not existing:
                break
            history_id = f"{now.strftime('%Y%m%d%H%M%S')}-{attempt + 1}"
        else:
            raise RuntimeError("Failed to generate unique history id")

        passed_count = sum(1 for r in results if r.get("passed", False))
        total_count = len(results)

        history = TestHistory(
            id=history_id,
            timestamp=now,
            api_name=api_name,
            report_name=report_name,
            total=total_count,
            passed=passed_count,
            failed=total_count - passed_count,
            status='completed',
            source='local',
            created_at=now
        )
        self.db.add(history)

        for r in results:
            test_result = TestResult(
                history_id=history_id,
                case_id=r.get('id') or r.get('case_id'),
                input=r.get('input'),
                actual_output=r.get('actual_output'),
                expected_output=r.get('expected_output'),
                retrieval_context=r.get('retrieval_context'),
                score=r.get('score'),
                reason=r.get('reason'),
                faithfulness_score=r.get('faithfulness_score'),
                faithfulness_reason=r.get('faithfulness_reason'),
                passed=r.get('passed', False),
                thinking=r.get('thinking'),
                inform_base=r.get('inform_base'),
                raw=r.get('raw'),
                latency=r.get('latency'),
                ttft=r.get('ttft'),
                type=r.get('type'),
                total_turns=r.get('total_turns'),
                passed_turns=r.get('passed_turns'),
                success_rate=r.get('success_rate'),
                overall_score=r.get('overall_score'),
                overall_passed=r.get('overall_passed'),
                turns=r.get('turns'),
                user_id=r.get('user_id'),
                session_id=r.get('session_id'),
                assertion_detail=r.get('assertion_detail'),
                category=r.get('category'),
                priority=r.get('priority'),
                module=r.get('module'),
                created_at=now
            )
            self.db.add(test_result)

        self.db.commit()
        return history_id

    def delete(self, history_ids: List[str]) -> int:
        """删除指定的 history（CASCADE 自动删除 results）"""
        count = self.db.query(TestHistory).filter(
            TestHistory.id.in_(history_ids)
        ).delete(synchronize_session=False)
        self.db.commit()
        return count

    def update_results(self, history_id: str, updated_results: List[Dict]) -> bool:
        """更新指定 history 的 results（用于 manual review 等）"""
        entry = self.db.query(TestHistory).filter(TestHistory.id == history_id).first()
        if not entry:
            return False

        # 获取现有 results，按顺序更新
        existing_results = self.db.query(TestResult).filter(
            TestResult.history_id == history_id
        ).order_by(TestResult.id).all()

        # 按 index 或 case_id+input 匹配更新
        for updated in updated_results:
            case_id = updated.get('id') or updated.get('case_id')
            input_text = updated.get('input')

            # 找到对应的 DB result
            target = None
            for er in existing_results:
                if er.case_id == case_id and er.input == input_text:
                    target = er
                    break

            if target:
                if 'passed' in updated:
                    target.passed = updated['passed']
                if 'review_comment' in updated:
                    target.reason = updated.get('reason', target.reason)
                if 'score' in updated:
                    target.score = updated['score']
                # Update Expect Result：同步 expected 值到报告数据
                if updated.get('expected_output') is not None:
                    target.expected_output = updated['expected_output']
                if updated.get('turns') is not None:
                    target.turns = updated['turns']

        # 重新计算 summary
        all_results = self.db.query(TestResult).filter(TestResult.history_id == history_id).all()
        passed_count = sum(1 for r in all_results if r.passed)
        entry.passed = passed_count
        entry.failed = entry.total - passed_count

        self.db.commit()
        return True

    def update_status(self, history_id: str, status: str, started_count: int = None) -> bool:
        """更新 history 状态（用于 running → completed）"""
        entry = self.db.query(TestHistory).filter(TestHistory.id == history_id).first()
        if not entry:
            return False
        entry.status = status
        if started_count is not None:
            entry.started_count = started_count
        self.db.commit()
        return True

    def _entry_to_dict(self, entry: TestHistory, include_results: bool = True) -> Dict:
        """将 ORM 对象转为 dict（兼容现有 report.py 格式）
        
        Args:
            include_results: 是否包含 results 详情
        """
        # ── 时间处理：DB 存的是 UTC naive datetime，显示转北京时间 (UTC+8) ──
        import datetime as _dt
        BJ_TZ = _dt.timezone(_dt.timedelta(hours=8))

        def _to_bj_str(dt_val):
            if not dt_val:
                return ''
            # DB 里的 datetime 是 naive UTC，先标记为 UTC 再转北京时间
            if dt_val.tzinfo is None:
                dt_val = dt_val.replace(tzinfo=_dt.timezone.utc)
            return dt_val.astimezone(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")

        def _calc_duration(start_dt, end_dt):
            """返回 "Xm Ys" / "Xh Ym" / "Xs" 形式的时长字符串"""
            if not start_dt or not end_dt:
                return ''
            delta = end_dt - start_dt
            total_sec = int(delta.total_seconds())
            if total_sec < 0:
                return ''
            if total_sec < 60:
                return f"{total_sec}s"
            minutes, sec = divmod(total_sec, 60)
            if minutes < 60:
                return f"{minutes}m {sec}s" if sec else f"{minutes}m"
            hours, minutes = divmod(minutes, 60)
            return f"{hours}h {minutes}m" if minutes else f"{hours}h"

        # 计算结束时间：
        # - completed/failed/cancelled/interrupted：用最后一条 result 的 created_at（若存在）
        # - running：用当前时间（显示实时耗时）
        start_dt = entry.timestamp
        end_dt = None
        if entry.status == 'running' and start_dt:
            end_dt = _dt.datetime.utcnow()
        elif start_dt and entry.status != 'running':
            # 单独查最后一条 result 的 created_at（不依赖 entry.results 是否被 relationship 加载）
            from app.models.test_history import TestResult
            last_r = self.db.query(TestResult.created_at).filter(
                TestResult.history_id == entry.id
            ).order_by(TestResult.id.desc()).first()
            if last_r and last_r[0]:
                end_dt = last_r[0]

        duration_str = _calc_duration(start_dt, end_dt) if start_dt else ''

        base_dict = {
            'id': entry.id,
            'timestamp': _to_bj_str(entry.timestamp),
            'duration': duration_str,
            'api_name': entry.api_name,
            'report_name': entry.report_name,
            'total': entry.total,
            'passed': entry.passed,
            'failed': entry.failed,
            'status': entry.status or 'completed',
            'started_count': entry.started_count or 0,
            'source': entry.source or 'local',
            'case_ids': entry.case_ids,
            'error_message': entry.error_message,
        }
        
        if include_results:
            results = []
            for r in entry.results:
                result_dict = {
                    'id': r.case_id,
                    'case_id': r.case_id,
                    'input': r.input,
                    'actual_output': r.actual_output,
                    'expected_output': r.expected_output,
                    'retrieval_context': r.retrieval_context,
                    'score': r.score,
                    'reason': r.reason,
                    'faithfulness_score': r.faithfulness_score,
                    'faithfulness_reason': r.faithfulness_reason,
                    'passed': r.passed,
                    'thinking': r.thinking,
                    'inform_base': r.inform_base,
                    'raw': r.raw,
                    'latency': r.latency,
                    'ttft': r.ttft,
                    'type': r.type,
                    'total_turns': r.total_turns,
                    'passed_turns': r.passed_turns,
                    'success_rate': r.success_rate,
                    'overall_score': r.overall_score,
                    'overall_passed': r.overall_passed,
                    'turns': r.turns,
                    'user_id': r.user_id,
                    'session_id': r.session_id,
                    'assertion_detail': r.assertion_detail,
                    'category': r.category,
                    'priority': r.priority,
                    'module': r.module,
                }
                results.append(result_dict)
            base_dict['results'] = results
        else:
            base_dict['results'] = []  # 占位，避免 KeyError
        
        return base_dict

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
