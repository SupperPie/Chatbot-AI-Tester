import pytest
import os
from dotenv import load_dotenv
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.models import GPTModel

load_dotenv(override=True)

import csv
from chat_client import get_chat_response

def get_test_cases():
    test_cases = []
    encodings = ['utf-8', 'gbk']
    
    for enc in encodings:
        try:
            with open("test_cases.csv", "r", encoding=enc) as f:
                reader = csv.DictReader(f)
                rows = list(reader) # Read all to force decode
                for row in rows:
                    test_cases.append(row)
            return test_cases
        except UnicodeDecodeError:
            continue
            
    raise ValueError("Could not decode test_cases.csv with utf-8 or gbk")

@pytest.mark.parametrize("case_data", get_test_cases())
def test_case(case_data):
    # Configure a custom model
    custom_model = GPTModel(
        model=os.getenv("OPENAI_MODEL_NAME", "deepseek-chat"), 
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
        api_key=os.getenv("OPENAI_API_KEY")
    )

    correctness_metric = GEval(
        name="Correctness",
        criteria="Determine if the 'actual output' is correct based on the 'expected output'.",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
        threshold=0.5,
        model=custom_model
    )
    
    input_text = case_data["input"]
    expected_output = case_data["expected_output"]
    context = [case_data["retrieval_context"]] if case_data.get("retrieval_context") else []
    
    # helper: handle empty context gracefully
    if context == [""]:
        context = []

    # Call the actual API
    actual_output = get_chat_response(input_text)
    print(f"\n[Input]: {input_text}")
    print(f"[Actual]: {actual_output}")
    print(f"[Expected]: {expected_output}")

    test_case = LLMTestCase(
        input=input_text,
        actual_output=actual_output,
        expected_output=expected_output,
        retrieval_context=context
    )
    
    # Measure directly to get access to score and reason
    correctness_metric.measure(test_case)
    
    # Log results to CSV
    result_file = "test_results.csv"
    file_exists = os.path.isfile(result_file)
    
    with open(result_file, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Input", "Actual Output", "Expected Output", "Context", "Score", "Reason", "Passed"])
        
        writer.writerow([
            input_text,
            actual_output,
            expected_output,
            context,
            correctness_metric.score,
            correctness_metric.reason,
            correctness_metric.is_successful()
        ])
        
    print(f"Result saved to {result_file}")

    # Assert correctness to fail the test in pytest if needed
    assert correctness_metric.is_successful(), f"Test failed with score {correctness_metric.score}. Reason: {correctness_metric.reason}"