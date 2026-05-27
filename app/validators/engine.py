"""
AssertionEngine - 断言引擎
从数据库加载组件定义，渲染参数，执行验证，汇总结果。
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from app.validators.base import BaseValidator, ValidationResult
from app.validators.field_validators import (
    FieldEqualsValidator, FieldContainsValidator, FieldMatchesValidator,
    FieldInValidator, FieldNotEmptyValidator, FieldTypeValidator,
    FieldCompareValidator, FieldLengthValidator,
)
from app.validators.structure_validators import (
    PathExistsValidator, RequiredFieldsValidator, FieldCountValidator,
    ArrayNotEmptyValidator, NestedStructureValidator,
)
from app.validators.status_validators import (
    StatusCodeEqualsValidator, StatusCodeInRangeValidator, StatusCodeNotEqualsValidator,
)


# ───────────── Validator 注册表 ─────────────

VALIDATOR_MAP: Dict[str, type] = {
    # field
    'field.equals': FieldEqualsValidator,
    'field.not_equals': FieldEqualsValidator,  # 通过 negate param 区分
    'field.contains': FieldContainsValidator,
    'field.matches': FieldMatchesValidator,
    'field.in': FieldInValidator,
    'field.not_empty': FieldNotEmptyValidator,
    'field.type': FieldTypeValidator,
    'field.gt': FieldCompareValidator,
    'field.gte': FieldCompareValidator,
    'field.lt': FieldCompareValidator,
    'field.lte': FieldCompareValidator,
    'field.length': FieldLengthValidator,
    # structure
    'structure.path_exists': PathExistsValidator,
    'structure.required_fields': RequiredFieldsValidator,
    'structure.field_count': FieldCountValidator,
    'structure.array_not_empty': ArrayNotEmptyValidator,
    'structure.nested_structure': NestedStructureValidator,
    # status_code
    'status_code.equals': StatusCodeEqualsValidator,
    'status_code.in_range': StatusCodeInRangeValidator,
    'status_code.not_equals': StatusCodeNotEqualsValidator,
}


@dataclass
class AssertionResult:
    component_id: str
    component_name: str
    passed: bool
    message: str
    details: Optional[dict] = None


@dataclass
class EngineResult:
    passed: bool
    score: float  # 通过率 0.0 ~ 1.0
    total: int
    passed_count: int
    results: List[AssertionResult] = field(default_factory=list)


class AssertionEngine:
    """断言执行引擎"""

    def __init__(self):
        self._component_cache: Dict[str, dict] = {}

    def run(self, response: dict, assertion_refs: List[dict],
            component_loader=None) -> EngineResult:
        """
        执行断言验证。

        Args:
            response: API 完整响应 JSON
            assertion_refs: 测试用例的 validation 字段解析后的列表
                           [{"ref": "AC001", "params": {...}}, ...]
            component_loader: 可选，从 DB 加载组件的函数 (id -> dict)
                             默认使用 AssertionService

        Returns:
            EngineResult
        """
        if not assertion_refs:
            return EngineResult(passed=True, score=1.0, total=0, passed_count=0)

        if component_loader is None:
            component_loader = self._default_loader

        results = []
        for ref_item in assertion_refs:
            comp_id = ref_item.get('ref')
            override_params = ref_item.get('params', {})

            comp_data = component_loader(comp_id)
            if comp_data is None:
                results.append(AssertionResult(
                    component_id=comp_id,
                    component_name='?',
                    passed=False,
                    message=f"Component '{comp_id}' not found",
                ))
                continue

            comp_results = self._execute_component(response, comp_data, override_params, component_loader)
            results.extend(comp_results)

        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        score = passed_count / total if total > 0 else 1.0
        return EngineResult(
            passed=(passed_count == total),
            score=score,
            total=total,
            passed_count=passed_count,
            results=results,
        )

    def run_local(self, response: dict, component_data: dict, params: dict = None) -> List[AssertionResult]:
        """
        本地验证：不从 DB 加载，直接传入组件定义执行。
        用于 UI 上的「本地验证」按钮。
        """
        return self._execute_component(response, component_data, params or {}, loader=None)

    def _execute_component(self, response: dict, comp_data: dict,
                           override_params: dict, loader) -> List[AssertionResult]:
        """执行单个组件（atomic 或 composite）"""
        category = comp_data['category']
        condition = comp_data['condition']
        config = comp_data.get('config', {})
        comp_id = comp_data.get('id', '?')
        comp_name = comp_data.get('name', '?')

        if category == 'composite':
            return self._execute_composite(response, comp_data, override_params, loader)

        # Atomic 组件
        params = self._render_params(config, override_params)
        # 参数别名标准化（兼容 AI 生成的不同命名）
        params = _normalize_params(category, params)

        # scope 处理：如果组件配置了 scope，从 __raw_lines__ 中筛选对应 type 的消息
        scope = config.get('scope') or params.pop('scope', None)
        effective_response = response
        if scope and '__raw_lines__' in response:
            effective_response = _filter_by_scope(response, scope)

        # not_equals 特殊处理
        if condition == 'not_equals':
            params['negate'] = True
            key = 'field.equals'
        elif condition in ('gt', 'gte', 'lt', 'lte'):
            params['operator'] = condition
            key = f'field.{condition}'
        else:
            key = f'{category}.{condition}'

        validator_cls = VALIDATOR_MAP.get(key)
        if validator_cls is None:
            return [AssertionResult(
                component_id=comp_id,
                component_name=comp_name,
                passed=False,
                message=f"No validator for '{key}'",
            )]

        # 验证必要参数是否存在
        required_params = _get_required_params(category, condition)
        missing = [p for p in required_params if p not in params]
        if missing:
            return [AssertionResult(
                component_id=comp_id,
                component_name=comp_name,
                passed=False,
                message=f"Missing required params: {missing}. Got: {list(params.keys())}",
            )]

        validator = validator_cls()
        try:
            result = validator.validate(effective_response, params)
        except Exception as e:
            result = ValidationResult(False, f"Validator error: {e}")

        return [AssertionResult(
            component_id=comp_id,
            component_name=comp_name,
            passed=result.passed,
            message=result.message,
            details=result.details,
        )]

    def _execute_composite(self, response: dict, comp_data: dict,
                           override_params: dict, loader) -> List[AssertionResult]:
        """执行 composite 组件：遍历 checks 数组"""
        config = comp_data.get('config', {})
        checks = config.get('checks', [])
        comp_id = comp_data.get('id', '?')
        comp_name = comp_data.get('name', '?')
        condition = comp_data.get('condition', 'all_pass')

        results = []
        for check in checks:
            if 'ref' in check:
                # 引用已有组件
                ref_id = check['ref']
                ref_params = check.get('params', {})
                if loader:
                    ref_data = loader(ref_id)
                    if ref_data:
                        sub_results = self._execute_component(response, ref_data, ref_params, loader)
                        results.extend(sub_results)
                    else:
                        results.append(AssertionResult(
                            component_id=ref_id,
                            component_name='?',
                            passed=False,
                            message=f"Referenced component '{ref_id}' not found",
                        ))
                else:
                    results.append(AssertionResult(
                        component_id=ref_id,
                        component_name='?',
                        passed=False,
                        message=f"Cannot load ref '{ref_id}' without loader",
                    ))
            else:
                # 内联检查
                inline_data = {
                    'id': f"{comp_id}.inline",
                    'name': f"{comp_name} (inline)",
                    'category': check.get('category', 'field'),
                    'condition': check.get('condition', 'equals'),
                    'config': {'params': check.get('params', {})},
                }
                sub_results = self._execute_component(response, inline_data, {}, loader)
                results.extend(sub_results)

        return results

    def _render_params(self, config: dict, override_params: dict) -> dict:
        """
        渲染参数：合并 config 中的 preset 参数和 override（deferred）参数。
        config 格式:
          {"params": {"field": "lob", "expected": "dc"}, "deferred_params": ["expected"]}
        """
        params = dict(config.get('params', {}))
        # override_params 覆盖 deferred 的值
        params.update(override_params)
        return params

    def _default_loader(self, component_id: str) -> Optional[dict]:
        """默认从 DB 加载组件"""
        if component_id in self._component_cache:
            return self._component_cache[component_id]

        from app.services.assertion_service import AssertionService
        service = AssertionService()
        comp = service.get_by_id(component_id)
        if comp is None:
            return None

        data = {
            'id': comp.id,
            'name': comp.name,
            'category': comp.category,
            'condition': comp.condition,
            'config': comp.config or {},
        }
        self._component_cache[component_id] = data
        return data


# ───────────── 参数校验辅助 ─────────────

_REQUIRED_PARAMS = {
    'field.equals': ['field', 'expected'],
    'field.not_equals': ['field', 'expected'],
    'field.contains': ['field', 'expected'],
    'field.matches': ['field', 'pattern'],
    'field.in': ['field', 'values'],
    'field.not_empty': ['field'],
    'field.type': ['field', 'expected_type'],
    'field.gt': ['field', 'value'],
    'field.gte': ['field', 'value'],
    'field.lt': ['field', 'value'],
    'field.lte': ['field', 'value'],
    'field.length': ['field', 'value'],
    'structure.path_exists': ['path'],
    'structure.required_fields': ['path', 'fields'],
    'structure.field_count': ['path', 'value'],
    'structure.array_not_empty': ['path'],
    'structure.nested_structure': ['path', 'fields'],
    'status_code.equals': ['expected'],
    'status_code.in_range': ['min', 'max'],
    'status_code.not_equals': ['expected'],
}


def _get_required_params(category: str, condition: str) -> list:
    """获取指定 category.condition 的必要参数列表"""
    key = f'{category}.{condition}'
    return _REQUIRED_PARAMS.get(key, [])


# 参数别名映射：AI 可能生成不同的 key 名称，统一转换为验证器期望的名称
_PARAM_ALIASES = {
    'field': {
        'path': 'field',           # AI 常用 path 代替 field
        'field_path': 'field',
        'value': 'expected',       # AI 常用 value 代替 expected
        'expected_value': 'expected',
        'target': 'field',
        'key': 'field',
    },
    'structure': {
        'field': 'path',           # structure 类用 path，AI 可能写成 field
        'field_path': 'path',
    },
    'status_code': {
        'value': 'expected',
        'code': 'expected',
        'status': 'expected',
    },
}


def _filter_by_scope(response: dict, scope: str) -> dict:
    """根据 scope 过滤 __raw_lines__，返回匹配 scope type 的数据作为新 response。

    scope 值: token, message, done, content 或自定义值
    匹配逻辑: raw_line.get('type') == scope
    如果匹配到多条，合并为列表；如果只有一条，直接返回该条作为 response。
    """
    raw_lines = response.get('__raw_lines__', [])
    matched = [line for line in raw_lines if line.get('type') == scope]

    if not matched:
        # 没有匹配的 scope，回退到完整 response（去掉 __raw_lines__ 避免干扰）
        fallback = {k: v for k, v in response.items() if k != '__raw_lines__'}
        return fallback

    if len(matched) == 1:
        return matched[0]

    # 多条匹配：合并（取最后一条为基础，附加 __items__ 列表）
    merged = dict(matched[-1])
    merged['__items__'] = matched
    return merged


def _normalize_params(category: str, params: dict) -> dict:
    """将 AI 生成的非标准参数名映射为验证器期望的标准名称"""
    aliases = _PARAM_ALIASES.get(category, {})
    if not aliases:
        return params

    normalized = {}
    for k, v in params.items():
        # 如果 key 在别名表中且目标 key 不存在，则转换
        standard_key = aliases.get(k)
        if standard_key and standard_key not in params and standard_key not in normalized:
            normalized[standard_key] = v
        else:
            normalized[k] = v
    return normalized
