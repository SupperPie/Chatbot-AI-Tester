import os
import time
import asyncio
import nest_asyncio
import pandas as pd
from typing import List, Dict, Any

# Ensure we can import chat client from root
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chat_client import get_chat_response
from dotenv import load_dotenv
load_dotenv(override=True)

try:
    from deepeval.metrics import GEval, FaithfulnessMetric
except ImportError:
    try:
        from deepeval.metrics.g_eval import GEval
        from deepeval.metrics.faithfulness import FaithfulnessMetric
    except ImportError:
        # Final fallback, maybe it was capitalized G in older versions?
        # Or missing. Let's assume user installed at least 0.20.x
        # If deeply missing, we just skip it or error out.
        # For now assume it's just import path
        print("Warning: Failed to import GEval. Trying legacy import paths.")
        # Attempt to proceed (it will fail later if not imported)
from deepeval.test_case import LLMTestCase
try:
    from deepeval.test_case import LLMTestCaseParams
except ImportError:
    # Older versions might not have this Enum
    class LLMTestCaseParams:
        INPUT = "input"
        ACTUAL_OUTPUT = "actual_output"
        EXPECTED_OUTPUT = "expected_output"
        CONTEXT = "context"
        RETRIEVAL_CONTEXT = "retrieval_context"
        

try:
    from deepeval.models import GPTModel
except ImportError:
    class GPTModel:
        def __init__(self, *args, **kwargs): pass

try:
    from deepeval import assert_test
except ImportError:
    # assert_test is for pytest integration, likely not used in our custom runner
    # Mock it just in case
    def assert_test(*args, **kwargs): pass

try:
    from deepeval.models.base_model import DeepEvalBaseLLM
except ImportError:
    # Fallback for very old versions or if models module missing
    try:
         # In some old versions it might be directly in deepeval.models? 
         # Or maybe deepeval.llm?
         # Just mock it for now to let app start
         class DeepEvalBaseLLM:
             def __init__(self, *args, **kwargs): pass
             def load_model(self): return self
             def generate(self, prompt): return "DeepEval model not loaded."
             async def a_generate(self, prompt): return "DeepEval model not loaded."
             def get_model_name(self): return "MockModel"
    except ImportError:
         class DeepEvalBaseLLM: pass
import openai

class SynchronousEvalModel(DeepEvalBaseLLM):
    def __init__(self, model_name, base_url, api_key):
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key
        
        # Check for OpenAI v1.x client availability
        if hasattr(openai, "OpenAI"):
            self.client = openai.OpenAI(
                base_url=base_url,
                api_key=api_key
            )
            self.is_v1 = True
        else:
            # Fallback for OpenAI v0.28.x
            self.client = None
            self.is_v1 = False
            # Note: In a multi-threaded app this global setting is risky, 
            # but for this simple deployment it's acceptable.
            openai.api_key = api_key
            openai.api_base = base_url

    def load_model(self):
        return self.client if self.is_v1 else self

    def generate(self, prompt: str) -> str:
        # Synchronous Generation
        try:
            if self.is_v1:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                content = response.choices[0].message.content
            else:
                # OpenAI v0.28.x syntax
                response = openai.ChatCompletion.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                content = response['choices'][0]['message']['content']
                
            # Clean up content to extract JSON for DeepEval
            import re
            content = content.strip()
            # Remove <think>...</think> if model is an R1 variant
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            
            # Extract JSON block from markdown if present
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                return json_match.group(1).strip()
            
            # fallback: attempt to find the last {} block
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return match.group(0).strip()
                
            return content
        except Exception as e:
            return f"Error: {e}"

    async def a_generate(self, prompt: str) -> str:
        # Even if called asynchronously, we block and run sync
        # to ensure safety in this precarious loop environment.
        return self.generate(prompt)

    def get_model_name(self):
        return self.model_name

class TestEngine:
    def __init__(self):
        # Use our custom Synchronous Model
        self.custom_model = SynchronousEvalModel(
            model_name=os.getenv("COMPATIBLE_MODEL", "qwen3-max"), 
            base_url=os.getenv("COMPATIBLE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            api_key=os.getenv("COMPATIBLE_API_KEY")
        )

        self.correctness_metric = GEval(
            name="Correctness",
            criteria="Determine if the 'actual output' is correct based on the 'expected output'.",
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            threshold=0.5,
            model=self.custom_model
        )
        
        # Faithfulness metric - checks if actual_output is faithful to retrieval_context
        self.faithfulness_metric = FaithfulnessMetric(
            threshold=0.5,
            model=self.custom_model
        )

    def run_case(self, case_data: Dict[str, Any], api_name: str = "Bundle API") -> Dict[str, Any]:
        """Runs a single test case and returns the result."""
        input_text = case_data.get("input")
        expected_output = case_data.get("expected_output")
        context = case_data.get("retrieval_context")
        
        # Sanitize input_text - handle NaN and convert to string
        # Check for various NaN types: None, float NaN, numpy NaN, string 'nan'
        def is_nan_value(val):
            if val is None:
                return True
            if isinstance(val, float):
                try:
                    return pd.isna(val)
                except:
                    return val != val  # NaN != NaN is True
            if isinstance(val, str) and val.lower() in ('nan', 'none', ''):
                return True
            return False
        
        if is_nan_value(input_text):
            return {"error": "Empty input", "id": case_data.get("id")}
        input_text = str(input_text)
        
        # Sanitize expected_output - handle NaN and convert to string
        if is_nan_value(expected_output):
            expected_output = "N/A"
        else:
            expected_output = str(expected_output)
        
        # Validate/Sanitize retrieval_context
        if context is None:
            context = []
        elif isinstance(context, float): # Handle NaN
             context = []
        elif isinstance(context, str):
             if context.strip():
                 context = [context] # Convert single string to list
             else:
                 context = []
        elif not isinstance(context, list):
             context = [] # Fallback for other types
             
        # Ensure all items in list are strings
        context = [str(c) for c in context if c is not None]
        
        if not input_text.strip():
             return {"error": "Empty input", "id": case_data.get("id")}

        # Initialize variables to avoid UnboundLocalError if API call fails
        thinking_process = None
        inform_base = None
        raw_data = None
        ttft = 0.0
        
        # Call API
        try:
            start_time = time.time()
            # Note: get_chat_response is synchronous.
            start_time = time.time()
            raw_response = get_chat_response(input_text, api_name=api_name)
            end_time = time.time()
            latency = end_time - start_time
            
            # Try to parse as structured JSON (with thinking process)
            try:
                import json
                resp_data = json.loads(raw_response)
                if isinstance(resp_data, dict) and "result" in resp_data:
                    actual_output = resp_data["result"]
                    thinking_process = resp_data.get("thinking")
                    inform_base = resp_data.get("inform_base")
                    raw_data = resp_data.get("raw")
                    ttft = float(resp_data.get("ttft", 0.0))
                else:
                    actual_output = raw_response
            except Exception:
                actual_output = raw_response
        except Exception as e:
            actual_output = f"Error calling API: {str(e)}"
            latency = 0.0

        is_error = actual_output.startswith("Error") or actual_output.startswith("❌ SERVER DETAIL") or "Error calling API:" in actual_output
        
        test_case = LLMTestCase(
            input=input_text,
            actual_output=actual_output,
            expected_output=expected_output,
            retrieval_context=context if context else None
        )

        score = 0.0
        reason = "Error occurred, evaluation skipped."
        faith_score = None
        faith_reason = None
        passed = False
        
        if not is_error:
            try:
                # deepeval's measure() internally uses asyncio.timeout which requires
                # running inside an async task. We use a_measure() with asyncio.run()
                # to create a proper async context.
                async def run_measure():
                    # Always run correctness metric
                    await self.correctness_metric.a_measure(test_case)
                    correctness_score = self.correctness_metric.score
                    correctness_reason = self.correctness_metric.reason
                    
                    # Run faithfulness metric only if retrieval_context is not empty
                    faith_score = None
                    faith_reason = None
                    if context:  # Only evaluate if context exists
                        try:
                            await self.faithfulness_metric.a_measure(test_case)
                            faith_score = self.faithfulness_metric.score
                            faith_reason = self.faithfulness_metric.reason
                        except Exception as e:
                            faith_reason = f"Faithfulness check failed: {str(e)}"
                    
                    # Calculate combined score
                    if faith_score is not None:
                        combined_score = (correctness_score + faith_score) / 2
                    else:
                        combined_score = correctness_score
                        
                    return (
                        combined_score,
                        correctness_reason,
                        faith_score,
                        faith_reason,
                        (combined_score >= 0.5)
                    )
                
                # Create a new event loop for each measurement to avoid conflicts
                score, reason, faith_score, faith_reason, passed = asyncio.run(run_measure())
            except Exception as e:
                score = 0
                reason = f"Metric calculation failed: {str(e)}"
                faith_score = None
                faith_reason = None
                passed = False

        return {
            "case_id": case_data.get("id"),
            "input": input_text,
            "actual_output": actual_output,
            "expected_output": expected_output,
            "score": score,
            "reason": reason,
            "faithfulness_score": faith_score,
            "faithfulness_reason": faith_reason,
            "faithfulness_reason": faith_reason,
            "passed": passed,
            "passed": passed,
            "thinking": thinking_process,
            "inform_base": inform_base,
            "raw": raw_data,
            "latency": latency,
            "ttft": ttft
        }

    def run_batch(self, cases: List[Dict[str, Any]], api_name: str = "Bundle API", on_step_complete=None, should_stop=None) -> List[Dict[str, Any]]:
        results = []
        
        # Group cases by ID to handle split multi-turn cases (rows with same ID)
        grouped_cases = {}
        single_cases = []
        
        for case in cases:
            case_id = case.get("id")
            case_type = case.get("type")
            
            # If explicitly multi_turn, group them
            if case_type == "multi_turn":
                if case_id not in grouped_cases:
                    grouped_cases[case_id] = []
                grouped_cases[case_id].append(case)
            else:
                single_cases.append(case)
        
        # Calculate total tasks for progress bar
        total_tasks = len(single_cases) + len(grouped_cases)
        completed_tasks = 0

        # Run single turn cases
        for case in single_cases:
            if should_stop and should_stop():
                break
            
            res = self.run_case(case, api_name=api_name)
            results.append(res)
            
            completed_tasks += 1
            if on_step_complete:
                on_step_complete(res, completed_tasks, total_tasks)
            
        # Run grouped multi-turn cases
        for case_id, group in grouped_cases.items():
            if should_stop and should_stop():
                break
            # Aggregate group into one case object
            # Sort by turn_index if available
            try:
                # Try to parse turn_index as int
                group.sort(key=lambda x: int(x.get("turn_index", 0)) if str(x.get("turn_index", "0")).isdigit() else 999)
            except:
                pass # Already in list order
            
            # Base case data from first row
            base_case = group[0].copy()
            
            # Construct conversation list from rows
            conversation_turns = []
            for i, row in enumerate(group):
                conversation_turns.append({
                    "turn": row.get("turn_index", i + 1),
                    "user": row.get("input", ""),
                    "expected": row.get("expected_output", ""),
                    "validation": row.get("validation", {"type": "semantic", "threshold": 0.5}),
                    "retrieval_context": row.get("retrieval_context", []),
                    "case_id": case_id # pass along case id for report rendering matching
                })
            
            base_case["conversation"] = conversation_turns
            
            # Remove any artifacts from the first row that don't apply to the whole group
            base_case["turn_index"] = None
            base_case["input"] = group[0].get("input", "") # For ID title purpose
            
            # Result depends on group execution
            res = self.run_multi_turn_case(base_case, api_name=api_name)
            results.append(res)
            
            completed_tasks += 1
            if on_step_complete:
                on_step_complete(res, completed_tasks, total_tasks)
            
        return results
    
    def run_multi_turn_case(self, case_data: Dict[str, Any], api_name: str = "Bundle API") -> Dict[str, Any]:
        """Runs a multi-turn conversation test case.
        
        Args:
            case_data: Test case with 'conversation' array containing turns
            api_name: Which API to use
            
        Returns:
            Dict with turn-by-turn results and overall score
        """
        import uuid
        
        conversation = case_data.get("conversation", [])
        if not conversation:
            return {"error": "No conversation turns defined", "case_id": case_data.get("id")}
        
        # Generate shared IDs for all turns in this conversation
        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())[:8]
        
        turn_results = []
        total_score = 0
        passed_turns = 0
        
        for turn in conversation:
            turn_num = turn.get("turn", len(turn_results) + 1)
            user_message = turn.get("user", "")
            expected = turn.get("expected", "")
            context = turn.get("retrieval_context", case_data.get("retrieval_context", []))
            
            # Fix: Parse validation if it's a string (JSON), handle NaN
            validation = turn.get("validation", {"type": "semantic", "threshold": 0.5})
            if isinstance(validation, float):
                validation = {"type": "semantic", "threshold": 0.5}
            elif isinstance(validation, str):
                try:
                    import json
                    validation = json.loads(validation.replace("'", "\"")) # Basic fix for single quotes
                except Exception:
                     validation = {"type": "semantic", "threshold": 0.5}
                     
            if not isinstance(validation, dict):
                validation = {"type": "semantic", "threshold": 0.5}
            
            if not user_message:
                turn_results.append({
                    "turn": turn_num,
                    "error": "Empty user message",
                    "passed": False
                })
                continue
            
            # Call API with shared session
            try:
                start_time = time.time()
                actual_output = get_chat_response(
                    user_message, 
                    api_name=api_name,
                    user_id=user_id,
                    session_id=session_id
                )
                end_time = time.time()
                turn_latency = end_time - start_time
                
                # Parse thinking process if available
                turn_thinking = None
                turn_inform_base = None
                ttft = 0.0
                try:
                    import json
                    resp_data = json.loads(actual_output)
                    if isinstance(resp_data, dict) and "result" in resp_data:
                        actual_output = resp_data["result"]
                        turn_thinking = resp_data.get("thinking")
                        turn_inform_base = resp_data.get("inform_base")
                        ttft = float(resp_data.get("ttft", 0.0))
                except Exception:
                    pass

            except Exception as e:
                actual_output = f"Error calling API: {str(e)}"
            
            # Evaluate based on validation type
            turn_passed = False
            turn_score = 0
            turn_reason = ""
            
            if validation.get("type") == "contains":
                # Keyword matching
                keywords = validation.get("keywords", [])
                matched = sum(1 for kw in keywords if kw.lower() in actual_output.lower())
                turn_score = matched / len(keywords) if keywords else 0
                turn_passed = turn_score >= validation.get("threshold", 0.5)
                turn_reason = f"Matched {matched}/{len(keywords)} keywords"
                
            elif validation.get("type") == "exact":
                # Exact match
                turn_passed = actual_output.strip() == expected.strip()
                turn_score = 1.0 if turn_passed else 0.0
                turn_reason = "Exact match" if turn_passed else "No exact match"
                
            else:  # semantic (default)
                is_error = actual_output.startswith("Error") or actual_output.startswith("❌ SERVER DETAIL") or "Error calling API:" in actual_output
                if is_error:
                    turn_score = 0.0
                    turn_reason = "Error occurred, evaluation skipped."
                    turn_passed = False
                else:
                    # Use GEval for semantic evaluation
                    test_case = LLMTestCase(
                        input=user_message,
                        actual_output=actual_output,
                        expected_output=expected,
                        retrieval_context=context if isinstance(context, list) else []
                    )
                    try:
                        async def eval_turn():
                            await self.correctness_metric.a_measure(test_case)
                            return self.correctness_metric.score, self.correctness_metric.reason
                        
                        # Create a new event loop for each measurement to avoid conflicts
                        turn_score, turn_reason = asyncio.run(eval_turn())
                        turn_passed = turn_score >= validation.get("threshold", 0.5)
                    except Exception as e:
                        turn_score = 0
                        turn_reason = f"Metric calculation failed: {str(e)}"
                        turn_passed = False
            
            turn_results.append({
                "turn": turn_num,
                "user": user_message,
                "expected": expected,
                "actual": actual_output,
                "score": turn_score,
                "reason": turn_reason,
                "passed": turn_passed,
                "passed": turn_passed,
                "thinking": turn_thinking,
                "inform_base": turn_inform_base,
                "latency": turn_latency,
                "ttft": ttft
            })
            
            total_score += turn_score
            if turn_passed:
                passed_turns += 1
        
        # Calculate overall results
        num_turns = len(conversation)
        overall_score = total_score / num_turns if num_turns > 0 else 0
        overall_passed = passed_turns == num_turns  # All turns must pass
        
        # Check overall criteria
        input_text = case_data.get("input") # First turn input as representative
        
        # Check overall criteria
        # Fix: Parse criteria if it's a string, handle NaN floats
        criteria = case_data.get("overall_criteria", {})
        if isinstance(criteria, float): # Handle Pandas NaN
            criteria = {}
        elif isinstance(criteria, str):
            try:
                import json
                criteria = json.loads(criteria.replace("'", "\""))
            except Exception:
                criteria = {}
        
        if not isinstance(criteria, dict):
            criteria = {}
                
        min_success_rate = criteria.get("min_success_rate", 1.0)
        success_rate = passed_turns / num_turns if num_turns > 0 else 0
        
        if not criteria.get("must_complete_all_turns", True):
            overall_passed = success_rate >= min_success_rate
        
        return {
            "case_id": case_data.get("id"),
            "input": input_text,
            "type": "multi_turn",
            "total_turns": num_turns,
            "passed_turns": passed_turns,
            "success_rate": success_rate,
            "score": overall_score,
            "reason": f"Multi-turn conversation ({num_turns} turns). Passed {passed_turns}/{num_turns}.",
            "overall_score": overall_score,
            "overall_passed": overall_passed,
            "overall_passed": overall_passed,
            "passed": overall_passed,
            "latency": sum(t.get("latency", 0) for t in turn_results),
            "ttft": sum(t.get("ttft", 0) for t in turn_results),
            "turns": turn_results,
            "user_id": user_id,
            "session_id": session_id
        }
