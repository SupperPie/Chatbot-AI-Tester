import re
from typing import Any
from app.validators.base import BaseValidator, ValidationResult


class FieldEqualsValidator(BaseValidator):
    """field / equals 或 not_equals"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']
        expected = params['expected']
        negate = params.get('negate', False)

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        # 类型对齐：尝试将 expected 转换为 actual 的类型
        expected_cast = _cast_value(expected, type(actual))

        if negate:
            passed = actual != expected_cast
            msg = f"'{field}' = {repr(actual)}, expected != {repr(expected_cast)}"
        else:
            passed = actual == expected_cast
            msg = f"'{field}' = {repr(actual)}, expected {repr(expected_cast)}"

        return ValidationResult(passed, msg)


class FieldContainsValidator(BaseValidator):
    """field / contains"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']
        substring = params['expected']

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        if isinstance(actual, str):
            passed = substring in actual
            msg = f"'{field}' {'contains' if passed else 'does not contain'} '{substring}'"
        elif isinstance(actual, (list, dict)):
            passed = substring in actual
            msg = f"'{field}' {'contains' if passed else 'does not contain'} {repr(substring)}"
        else:
            return ValidationResult(False, f"Field '{field}' is type {type(actual).__name__}, cannot check contains")

        return ValidationResult(passed, msg)


class FieldMatchesValidator(BaseValidator):
    """field / matches (正则匹配)"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']
        pattern = params['pattern']

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        if not isinstance(actual, str):
            actual = str(actual)

        passed = bool(re.search(pattern, actual))
        msg = f"'{field}' = {repr(actual)}, pattern /{pattern}/ {'matched' if passed else 'not matched'}"
        return ValidationResult(passed, msg)


class FieldInValidator(BaseValidator):
    """field / in (值在列表中)"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']
        values = params['values']  # list

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        passed = actual in values
        msg = f"'{field}' = {repr(actual)}, {'in' if passed else 'not in'} {values}"
        return ValidationResult(passed, msg)


class FieldNotEmptyValidator(BaseValidator):
    """field / not_empty"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        if actual is None or actual == '' or actual == [] or actual == {}:
            return ValidationResult(False, f"Field '{field}' is empty (value: {repr(actual)})")

        return ValidationResult(True, f"Field '{field}' is not empty (value: {repr(actual)[:80]})")


class FieldTypeValidator(BaseValidator):
    """field / type (类型检查)"""

    TYPE_MAP = {
        'str': str, 'string': str,
        'int': int, 'integer': int,
        'float': float, 'number': (int, float),
        'bool': bool, 'boolean': bool,
        'list': list, 'array': list,
        'dict': dict, 'object': dict,
        'null': type(None), 'none': type(None),
    }

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']
        expected_type = params['expected_type']

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        target_type = self.TYPE_MAP.get(expected_type.lower())
        if target_type is None:
            return ValidationResult(False, f"Unknown type '{expected_type}'")

        passed = isinstance(actual, target_type)
        msg = f"'{field}' is {type(actual).__name__}, expected {expected_type}"
        return ValidationResult(passed, msg)


class FieldCompareValidator(BaseValidator):
    """field / gt, gte, lt, lte (数值比较)"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']
        operator = params['operator']  # gt / gte / lt / lte
        value = params['value']

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        try:
            actual_num = float(actual)
            value_num = float(value)
        except (ValueError, TypeError):
            return ValidationResult(False, f"Cannot compare: actual={repr(actual)}, value={repr(value)}")

        ops = {
            'gt': actual_num > value_num,
            'gte': actual_num >= value_num,
            'lt': actual_num < value_num,
            'lte': actual_num <= value_num,
        }
        passed = ops.get(operator, False)
        msg = f"'{field}' = {actual_num} {operator} {value_num} -> {passed}"
        return ValidationResult(passed, msg)


class FieldLengthValidator(BaseValidator):
    """field / length (长度/数量检查)"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        field = params['field']
        operator = params.get('operator', 'gte')
        value = int(params['value'])

        try:
            actual = self.extract_field(response, field)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Field '{field}' not found: {e}")

        if not hasattr(actual, '__len__'):
            return ValidationResult(False, f"Field '{field}' has no length (type: {type(actual).__name__})")

        length = len(actual)
        ops = {
            'eq': length == value,
            'gt': length > value,
            'gte': length >= value,
            'lt': length < value,
            'lte': length <= value,
        }
        passed = ops.get(operator, False)
        msg = f"'{field}' length={length}, {operator} {value} -> {passed}"
        return ValidationResult(passed, msg)


def _cast_value(value: Any, target_type: type) -> Any:
    """尝试类型转换，失败则返回原值"""
    if isinstance(value, target_type):
        return value
    try:
        if target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        elif target_type == bool:
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes')
            return bool(value)
        elif target_type == str:
            return str(value)
    except (ValueError, TypeError):
        pass
    return value
