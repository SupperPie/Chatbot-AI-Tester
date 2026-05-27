from app.validators.base import BaseValidator, ValidationResult


class PathExistsValidator(BaseValidator):
    """structure / path_exists"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        path = params['path']
        if self.field_exists(response, path):
            return ValidationResult(True, f"Path '{path}' exists")
        return ValidationResult(False, f"Path '{path}' does not exist")


class RequiredFieldsValidator(BaseValidator):
    """structure / required_fields"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        path = params.get('path', '.')
        fields = params['fields']  # list of field names

        try:
            target = self.extract_field(response, path)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Path '{path}' not found: {e}")

        if not isinstance(target, dict):
            return ValidationResult(False, f"Value at '{path}' is not a dict (type: {type(target).__name__})")

        missing = [f for f in fields if f not in target]
        if missing:
            return ValidationResult(False, f"Missing fields at '{path}': {missing}")
        return ValidationResult(True, f"All required fields present: {', '.join(fields)}")


class FieldCountValidator(BaseValidator):
    """structure / field_count"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        path = params.get('path', '.')
        operator = params.get('operator', 'gte')
        value = int(params['value'])

        try:
            target = self.extract_field(response, path)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Path '{path}' not found: {e}")

        if not isinstance(target, dict):
            return ValidationResult(False, f"Value at '{path}' is not a dict")

        count = len(target)
        ops = {
            'eq': count == value,
            'gt': count > value,
            'gte': count >= value,
            'lt': count < value,
            'lte': count <= value,
        }
        passed = ops.get(operator, False)
        return ValidationResult(passed, f"Field count at '{path}' = {count}, {operator} {value} -> {passed}")


class ArrayNotEmptyValidator(BaseValidator):
    """structure / array_not_empty"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        path = params['path']

        try:
            target = self.extract_field(response, path)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Path '{path}' not found: {e}")

        if not isinstance(target, list):
            return ValidationResult(False, f"Value at '{path}' is not an array (type: {type(target).__name__})")

        if len(target) == 0:
            return ValidationResult(False, f"Array at '{path}' is empty")
        return ValidationResult(True, f"Array at '{path}' has {len(target)} element(s)")


class NestedStructureValidator(BaseValidator):
    """structure / nested_structure - 检查嵌套结构中每个元素是否包含指定字段"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        path = params['path']
        fields = params['fields']  # 每个数组元素需要包含的字段

        try:
            target = self.extract_field(response, path)
        except (KeyError, IndexError, TypeError) as e:
            return ValidationResult(False, f"Path '{path}' not found: {e}")

        if not isinstance(target, list):
            return ValidationResult(False, f"Value at '{path}' is not an array")

        if len(target) == 0:
            return ValidationResult(False, f"Array at '{path}' is empty, cannot check structure")

        errors = []
        for i, item in enumerate(target):
            if not isinstance(item, dict):
                errors.append(f"[{i}] is not a dict")
                continue
            missing = [f for f in fields if f not in item]
            if missing:
                errors.append(f"[{i}] missing: {missing}")

        if errors:
            return ValidationResult(False, f"Nested structure check failed at '{path}': {'; '.join(errors[:3])}")
        return ValidationResult(True, f"All {len(target)} items at '{path}' have fields: {', '.join(fields)}")
