# Import all models to ensure SQLAlchemy relationship resolution
from app.models.category import Category  # noqa: F401
from app.models.test_case import TestCase  # noqa: F401
from app.models.test_history import TestHistory, TestResult  # noqa: F401
from app.models.assertion_component import AssertionComponent  # noqa: F401
