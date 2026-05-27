from app.validators.base import BaseValidator, ValidationResult


class StatusCodeEqualsValidator(BaseValidator):
    """status_code / equals"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        expected = int(params['expected'])
        actual = response.get('status_code')

        if actual is None:
            return ValidationResult(False, "No 'status_code' in response")

        actual = int(actual)
        passed = actual == expected
        msg = f"status_code = {actual}, expected {expected}"
        return ValidationResult(passed, msg)


class StatusCodeInRangeValidator(BaseValidator):
    """status_code / in_range"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        min_code = int(params.get('min', 200))
        max_code = int(params.get('max', 299))
        actual = response.get('status_code')

        if actual is None:
            return ValidationResult(False, "No 'status_code' in response")

        actual = int(actual)
        passed = min_code <= actual <= max_code
        msg = f"status_code = {actual}, range [{min_code}, {max_code}] -> {passed}"
        return ValidationResult(passed, msg)


class StatusCodeNotEqualsValidator(BaseValidator):
    """status_code / not_equals"""

    def validate(self, response: dict, params: dict) -> ValidationResult:
        expected = int(params['expected'])
        actual = response.get('status_code')

        if actual is None:
            return ValidationResult(False, "No 'status_code' in response")

        actual = int(actual)
        passed = actual != expected
        msg = f"status_code = {actual}, expected != {expected}"
        return ValidationResult(passed, msg)
