from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, List
from jsonpath_ng.ext import parse as jsonpath_parse


@dataclass
class ValidationResult:
    passed: bool
    message: str
    details: Optional[dict] = None


class BaseValidator(ABC):
    """断言验证器基类"""

    @abstractmethod
    def validate(self, response: dict, params: dict) -> ValidationResult:
        """
        执行验证逻辑。
        
        Args:
            response: API 返回的完整 JSON 响应
            params: 已渲染的参数（preset + deferred 合并后）
        
        Returns:
            ValidationResult
        """
        pass

    @staticmethod
    def extract_field(data: Any, path: str) -> Any:
        """
        从嵌套数据中提取字段值，支持 JSONPath 语法 + 智能降级。
        
        支持格式（按优先级）:
          1. JSONPath 标准语法:
             - "$.data.bundle_list[0].name"  → 绝对路径
             - "$..bundle_name"              → 递归搜索
             - "$.data.flights[*].price"     → 数组通配
          2. 简写路径（自动转换）:
             - "data.bundle_list[0].name"    → 先当绝对路径尝试，失败则递归
             - "bundle_name"                 → 递归搜索 $..bundle_name
          3. 特殊值:
             - "." 或 ""                     → 返回整个 data
        
        Returns:
            匹配到的值。如果 JSONPath 返回多个匹配，返回第一个。
        Raises:
            KeyError: 路径不存在
        """
        if path == "." or path == "":
            return data

        # 策略 1: 如果是标准 JSONPath（以 $ 开头），直接解析
        if path.startswith("$"):
            return _jsonpath_extract(data, path)

        # 策略 2: 简写路径 → 先尝试绝对路径 $.path，再降级为递归 $..leaf
        absolute_expr = f"$.{path}"
        try:
            return _jsonpath_extract(data, absolute_expr)
        except KeyError:
            pass

        # 策略 3: 递归搜索（取路径最后一段作为搜索目标）
        # 例如 "data.bundle_list[0].bundle_name" 失败后，搜索 $..bundle_name
        leaf = path.rsplit(".", 1)[-1] if "." in path else path
        # 清理数组索引: "bundle_list[0]" → "bundle_list"
        leaf_clean = leaf.split("[")[0] if "[" in leaf else leaf
        recursive_expr = f"$..{leaf_clean}"
        try:
            return _jsonpath_extract(data, recursive_expr)
        except KeyError:
            raise KeyError(f"Path '{path}' not found (tried: {absolute_expr}, {recursive_expr})")

    @staticmethod
    def extract_field_all(data: Any, path: str) -> List[Any]:
        """
        提取所有匹配的值（用于数组通配 [*] 等场景）。
        返回列表，可能为空。
        """
        if path == "." or path == "":
            return [data]

        if path.startswith("$"):
            expr = path
        else:
            expr = f"$.{path}"

        try:
            parsed = jsonpath_parse(expr)
            matches = parsed.find(data)
            if matches:
                return [m.value for m in matches]
        except Exception:
            pass

        # 递归搜索
        leaf = path.rsplit(".", 1)[-1] if "." in path else path
        leaf_clean = leaf.split("[")[0] if "[" in leaf else leaf
        try:
            parsed = jsonpath_parse(f"$..{leaf_clean}")
            matches = parsed.find(data)
            return [m.value for m in matches] if matches else []
        except Exception:
            return []

    @staticmethod
    def field_exists(data: Any, path: str) -> bool:
        """检查路径是否存在"""
        try:
            BaseValidator.extract_field(data, path)
            return True
        except (KeyError, IndexError, TypeError):
            return False


def _jsonpath_extract(data: Any, expr: str) -> Any:
    """
    使用 JSONPath 表达式提取值。
    返回第一个匹配结果。如果无匹配，抛出 KeyError。
    """
    try:
        parsed = jsonpath_parse(expr)
        matches = parsed.find(data)
        if not matches:
            raise KeyError(f"JSONPath '{expr}' matched nothing")
        # 返回第一个匹配值
        return matches[0].value
    except KeyError:
        raise
    except Exception as e:
        raise KeyError(f"JSONPath '{expr}' error: {e}")
