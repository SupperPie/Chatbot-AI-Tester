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

# ---------- API call retry helper (Task: job-resilience-and-continue) ----------
# 对瞬时网络异常做 3 次指数退避重试；业务返回的错误字符串（"Error: ..."）不重试，
# 因为那是被测系统的业务错误，重试无意义。
def _call_chat_with_retry(*args, max_retries: int = 3, base_delay: float = 1.0, **kwargs):
    """Wrap get_chat_response with retry on transient network exceptions.

    Retries on requests-level exceptions (ConnectionError/Timeout) and bare
    ConnectionError/TimeoutError. Other exceptions (e.g. value errors, business
    logic) propagate immediately.
    """
    try:
        import requests as _requests
        retry_excs = (
            _requests.exceptions.ConnectionError,
            _requests.exceptions.Timeout,
            _requests.exceptions.ChunkedEncodingError,
            ConnectionError,
            TimeoutError,
        )
    except ImportError:
        retry_excs = (ConnectionError, TimeoutError)

    last_exc = None
    for attempt in range(max_retries):
        try:
            return get_chat_response(*args, **kwargs)
        except retry_excs as e:
            last_exc = e
            if attempt < max_retries - 1:
                sleep_s = base_delay * (2 ** attempt)
                print(f"[retry] API call failed ({type(e).__name__}: {e}), retry {attempt + 1}/{max_retries - 1} after {sleep_s}s")
                time.sleep(sleep_s)
            continue
    raise RuntimeError(f"API call failed after {max_retries} retries: {last_exc}")
# -------------------------------------------------------------------------------

load_dotenv(override=True)

GEval = None
FaithfulnessMetric = None
ConversationalGEval = None
try:
    from deepeval.metrics import GEval, FaithfulnessMetric
except ImportError:
    try:
        from deepeval.metrics.g_eval import GEval
        from deepeval.metrics.faithfulness import FaithfulnessMetric
    except ImportError:
        # Both import paths failed — leave GEval and FaithfulnessMetric as None
        # so the rest of the code can check for None safely.
        print("Warning: Failed to import GEval and FaithfulnessMetric. Metrics will be skipped.")

# Import ConversationalGEval for multi-turn evaluation
try:
    from deepeval.metrics import ConversationalGEval
except ImportError:
    try:
        from deepeval.metrics.conversational_g_eval import ConversationalGEval
    except ImportError:
        print("Warning: Failed to import ConversationalGEval. Multi-turn evaluation will use fallback.")
try:
    from deepeval.test_case import LLMTestCase
except ImportError:
    # Provide a stub so the engine can still run and report failures gracefully
    class LLMTestCase:
        def __init__(self, input="", actual_output="", expected_output="", retrieval_context=None, **kwargs):
            self.input = input
            self.actual_output = actual_output
            self.expected_output = expected_output
            self.retrieval_context = retrieval_context or []

# Import ConversationalTestCase and Turn for multi-turn evaluation
ConversationalTestCase = None
Turn = None
try:
    from deepeval.test_case import ConversationalTestCase, Turn
except ImportError:
    print("Warning: Failed to import ConversationalTestCase/Turn. Multi-turn evaluation will use fallback.")
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
    # deepeval 3.x: prefer from deepeval.models
    from deepeval.models import DeepEvalBaseLLM
except ImportError:
    try:
        # Fallback for older versions
        from deepeval.models.base_model import DeepEvalBaseLLM
    except ImportError:
        # Mock it for environments without deepeval
        class DeepEvalBaseLLM:
            def __init__(self, *args, **kwargs): pass
            def load_model(self): return self
            def generate(self, prompt): return "DeepEval model not loaded."
            async def a_generate(self, prompt): return "DeepEval model not loaded."
            def get_model_name(self): return "MockModel"
import openai


def _safe_str(v) -> str:
    """将 pandas 读出的 NaN/None/数值等安全转为非空 str，空值返回 ''。"""
    if v is None:
        return ""
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    s = str(v).strip()
    if s in ("", "nan", "None", "NaN"):
        return ""
    return s


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
    _instance = None  # 模块级单例：避免每次 Run 都重新初始化 DeepEval 指标

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        # Use our custom Synchronous Model
        self.custom_model = SynchronousEvalModel(
            model_name=os.getenv("COMPATIBLE_MODEL", "qwen3-max"), 
            base_url=os.getenv("COMPATIBLE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            api_key=os.getenv("COMPATIBLE_API_KEY")
        )

        # Initialize metrics safely — deepeval may be missing or incompatible on this server
        self.correctness_metric = None
        self.faithfulness_metric = None
        try:
            if GEval is not None:
                self.correctness_metric = GEval(
                    name="Correctness",
                    criteria="Determine if the 'actual output' is correct based on the 'expected output'.",
                    evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                    threshold=0.5,
                    model=self.custom_model
                )
        except Exception as e:
            print(f"WARNING: GEval metric initialization failed: {e}. Correctness scoring will be skipped.")
            self.correctness_metric = None

        try:
            if FaithfulnessMetric is not None:
                self.faithfulness_metric = FaithfulnessMetric(
                    threshold=0.5,
                    model=self.custom_model
                )
        except Exception as e:
            print(f"WARNING: FaithfulnessMetric initialization failed: {e}. Faithfulness scoring will be skipped.")
            self.faithfulness_metric = None
        
        # Initialize ConversationalGEval for multi-turn evaluation
        self.conversational_metric = None
        try:
            if ConversationalGEval is not None:
                self.conversational_metric = ConversationalGEval(
                    name="Correctness",
                    criteria="Determine if the assistant's responses throughout the conversation are correct, helpful, and contextually appropriate based on the user's queries and expected outcomes.",
                    threshold=0.5,
                    model=self.custom_model
                )
        except Exception as e:
            print(f"WARNING: ConversationalGEval initialization failed: {e}. Multi-turn will use fallback scoring.")
            self.conversational_metric = None

        # 注：原来这里会 _warmup_metrics() 同步发 2 次 LLM 请求预热，这是每次点击 Run
        # 都卡顿的主因。DeepEval 指标对象构造只是存配置（不发网络请求），真正的 LLM
        # 调用发生在 a_measure() 评分时，首条用例评分稍慢是可接受的。


    @staticmethod
    def _extract_assertion_response(raw_data, raw_response, actual_output) -> dict:
        """
        从 API 响应中构建用于断言验证的合并对象。
        - 解析 NDJSON 得到所有行 (__raw_lines__)
        - 默认取 type=done 消息作为主体（包含完整 data）
        - 附加 __raw_lines__ 供 scope 过滤使用
        - 附加 result 字段（拼接的完整文本）
        """
        import json as _json

        all_lines = []

        # 1. 尝试解析 raw_data 为 NDJSON
        if raw_data and isinstance(raw_data, str):
            for line in raw_data.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                    if isinstance(obj, dict):
                        all_lines.append(obj)
                except _json.JSONDecodeError:
                    continue

        if all_lines:
            # 找 done 消息作为主体
            done_msg = next((l for l in all_lines if l.get("type") == "done"), None)
            base = dict(done_msg) if done_msg else dict(all_lines[-1])
            # 附加 raw_lines 供 scope 过滤
            base['__raw_lines__'] = all_lines
            # 附加拼接的完整文本（兼容内部接口 type=token 和 portal_im type=content 两种 SSE 格式）
            if 'result' not in base:
                tokens = []
                for l in all_lines:
                    if l.get("type") in ("token", "content") and not l.get("is_thinking"):
                        d = l.get("data") or l.get("content")
                        if isinstance(d, str):
                            tokens.append(d)
                if tokens:
                    base['result'] = ''.join(tokens)
                elif actual_output:
                    base['result'] = actual_output
            return base

        # 2. 尝试直接解析 raw_data 为单个 JSON
        if raw_data:
            try:
                parsed = _json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                if isinstance(parsed, dict):
                    parsed['__raw_lines__'] = [parsed]
                    return parsed
            except Exception:
                pass

        # 3. Fallback: 解析 raw_response
        if raw_response:
            try:
                parsed = _json.loads(raw_response) if isinstance(raw_response, str) else {}
                if isinstance(parsed, dict):
                    parsed['__raw_lines__'] = [parsed]
                    return parsed
            except Exception:
                pass

        # 4. 最终 fallback
        fallback = {"result": actual_output}
        fallback['__raw_lines__'] = [fallback]
        return fallback

    def run_case(self, case_data: Dict[str, Any], api_name: str = "Skills", execution_mode: str = "full", should_stop=None) -> Dict[str, Any]:
        """Runs a single test case and returns the result.
        
        execution_mode: "semantic" | "assertion" | "full"
        """
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
        raw_response = None
        ttft = 0.0
        
        # Call API
        try:
            start_time = time.time()
            # Note: get_chat_response is synchronous.
            start_time = time.time()
            raw_response = _call_chat_with_retry(input_text, api_name=api_name)
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

        # ─── 准备断言和语义评分的数据 ───
        assertion_refs = case_data.get("assertions")  # JSONB list from DB
        # 兼容字符串格式（从 DataFrame to_dict 可能序列化为 str）
        if isinstance(assertion_refs, str):
            try:
                import json as _json_parse
                assertion_refs = _json_parse.loads(assertion_refs)
            except Exception:
                assertion_refs = None
        
        run_assertions = execution_mode in ("assertion", "full") and assertion_refs and not is_error
        run_semantic = execution_mode in ("semantic", "full") and not is_error

        test_case = LLMTestCase(
            input=input_text,
            actual_output=actual_output,
            expected_output=expected_output,
            retrieval_context=context if context else None
        )

        # ─── 并行执行断言引擎和语义评分 ───
        import concurrent.futures

        def _run_assertion_engine():
            """在线程池中运行断言引擎"""
            try:
                from app.validators.engine import AssertionEngine
                _response_for_assert = self._extract_assertion_response(raw_data, raw_response, actual_output)
                engine = AssertionEngine()
                engine_result = engine.run(_response_for_assert, assertion_refs)
                return {
                    "mode": execution_mode,
                    "passed": engine_result.passed,
                    "score": engine_result.score,
                    "total": engine_result.total,
                    "passed_count": engine_result.passed_count,
                    "results": [
                        {"id": r.component_id, "name": r.component_name,
                         "passed": r.passed, "message": r.message}
                        for r in engine_result.results
                    ]
                }
            except Exception as e:
                return {
                    "mode": execution_mode,
                    "passed": False,
                    "score": 0,
                    "total": 0,
                    "passed_count": 0,
                    "results": [{"id": "?", "name": "engine_error", "passed": False, "message": str(e)}]
                }

        def _run_semantic():
            """在线程池中运行语义评分"""
            async def _run_semantic_async(tc, has_context, correctness_m, faithfulness_m):
                """运行语义评分（async）"""
                if correctness_m is None:
                    return (0.0, "DeepEval GEval metric not available on this server.", None, None, False)

                await correctness_m.a_measure(tc)
                correctness_score = correctness_m.score
                correctness_reason = correctness_m.reason

                # 在两个 metric 之间检查 stop：若已请求停止，跳过 faithfulness
                if should_stop and should_stop():
                    return (correctness_score, correctness_reason, None, "Cancelled before faithfulness", (correctness_score >= 0.5))

                faith_score = None
                faith_reason = None
                if has_context and faithfulness_m is not None:
                    try:
                        await faithfulness_m.a_measure(tc)
                        faith_score = faithfulness_m.score
                        faith_reason = faithfulness_m.reason
                    except Exception as e:
                        faith_reason = f"Faithfulness check failed: {str(e)}"
                
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
            
            try:
                return asyncio.run(_run_semantic_async(
                    test_case, bool(context), self.correctness_metric, self.faithfulness_metric
                ))
            except Exception as e:
                return (0.0, f"Metric calculation failed: {str(e)}", None, None, False)

        # 并行执行
        assertion_detail = None
        score, reason, faith_score, faith_reason, passed = 0.0, "Error occurred, evaluation skipped.", None, None, False

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            if run_assertions:
                futures['assertion'] = executor.submit(_run_assertion_engine)
            if run_semantic:
                futures['semantic'] = executor.submit(_run_semantic)

            # 等待结果
            for name, future in futures.items():
                try:
                    result = future.result(timeout=300)  # 5分钟超时
                    if name == 'assertion':
                        assertion_detail = result
                    else:
                        score, reason, faith_score, faith_reason, passed = result
                    # 收到取消信号立即短路后续 futures，避免继续等待
                    if should_stop and should_stop():
                        break
                except concurrent.futures.TimeoutError:
                    if name == 'assertion':
                        assertion_detail = {"passed": False, "score": 0, "total": 0, "passed_count": 0, 
                                          "results": [{"id": "?", "name": "timeout", "passed": False, "message": "Assertion engine timeout"}]}
                    else:
                        score, reason, passed = 0.0, "Semantic evaluation timeout", False
                except Exception as e:
                    if name == 'assertion':
                        assertion_detail = {"passed": False, "score": 0, "total": 0, "passed_count": 0,
                                          "results": [{"id": "?", "name": "error", "passed": False, "message": str(e)}]}
                    else:
                        score, reason, passed = 0.0, f"Semantic evaluation error: {e}", False

        # ─── 综合 passed 判定 ───
        if execution_mode == "assertion":
            passed = assertion_detail["passed"] if assertion_detail else True
        elif execution_mode == "full" and assertion_detail:
            passed = passed and assertion_detail["passed"]
        # semantic mode: passed 已经在上面计算好了

        return {
            "case_id": case_data.get("id"),
            "input": input_text,
            "actual_output": actual_output,
            "expected_output": expected_output,
            "retrieval_context": ", ".join(context) if isinstance(context, list) else str(context or ""),
            "score": score,
            "reason": reason,
            "faithfulness_score": faith_score,
            "faithfulness_reason": faith_reason,
            "passed": passed,
            "thinking": thinking_process,
            "inform_base": inform_base,
            "raw": raw_data,
            "latency": latency,
            "ttft": ttft,
            "assertion_detail": assertion_detail,
            "category": case_data.get("category"),
            "priority": case_data.get("priority"),
        }

    def run_batch(self, cases: List[Dict[str, Any]], api_name: str = "Skills", on_step_complete=None, should_stop=None, execution_mode: str = "full", max_workers: int = 1) -> List[Dict[str, Any]]:
        import concurrent.futures
        import threading

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
        completed_lock = threading.Lock()

        def _run_single_case_safe(case):
            """Wrapper: check stop before start, catch exceptions to avoid poisoning the pool."""
            if should_stop and should_stop():
                return None
            try:
                return self.run_case(case, api_name=api_name, execution_mode=execution_mode, should_stop=should_stop)
            except Exception as e:
                # 兜底：单个 case 失败不能拖垮整个池
                return {
                    "case_id": case.get("id"),
                    "turn_index": case.get("turn_index"),
                    "input": case.get("input", ""),
                    "expected_output": case.get("expected_output", ""),
                    "actual_output": "",
                    "retrieval_context": "",
                    "score": 0,
                    "reason": f"Exception in run_case: {e}",
                    "passed": False,
                    "thinking": "",
                    "inform_base": "",
                    "raw": "",
                    "latency": 0,
                    "ttft": 0,
                    "assertion_detail": None,
                    "category": case.get("category"),
                    "priority": case.get("priority"),
                }

        # Run single turn cases (并发或串行)
        if max_workers and max_workers > 1 and len(single_cases) > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="run_case",
            ) as pool:
                futures = {pool.submit(_run_single_case_safe, c): c for c in single_cases}
                try:
                    for fut in concurrent.futures.as_completed(futures):
                        if should_stop and should_stop():
                            # 取消尚未开始的任务；正在执行的会自然结束
                            for f in futures:
                                f.cancel()
                            break
                        res = fut.result()
                        if res is None:
                            continue
                        results.append(res)
                        with completed_lock:
                            completed_tasks += 1
                            idx = completed_tasks
                        if on_step_complete:
                            try:
                                on_step_complete(res, idx, total_tasks)
                            except Exception:
                                pass
                except Exception:
                    # 主循环异常，取消未启动任务后重抛
                    for f in futures:
                        f.cancel()
                    raise
        else:
            for case in single_cases:
                if should_stop and should_stop():
                    break
                res = self.run_case(case, api_name=api_name, execution_mode=execution_mode, should_stop=should_stop)
                results.append(res)
                completed_tasks += 1
                if on_step_complete:
                    on_step_complete(res, completed_tasks, total_tasks)
            
        # Run grouped multi-turn cases —— 保持串行（多轮上下文依赖顺序）
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
            res = self.run_multi_turn_case(base_case, api_name=api_name, should_stop=should_stop)
            results.append(res)
            
            completed_tasks += 1
            if on_step_complete:
                on_step_complete(res, completed_tasks, total_tasks)
            
        return results
    
    def run_multi_turn_case(self, case_data: Dict[str, Any], api_name: str = "Skills", should_stop=None) -> Dict[str, Any]:
        """Runs a multi-turn conversation test case using ConversationalGEval for overall scoring.
        
        Args:
            case_data: Test case with 'conversation' array containing turns
            api_name: Which API to use
            
        Returns:
            Dict with turn-by-turn results and overall score from ConversationalGEval
        """
        import uuid
        import json
        
        conversation = case_data.get("conversation", [])
        if not conversation:
            return {"error": "No conversation turns defined", "case_id": case_data.get("id")}
        
        # Generate shared IDs for all turns in this conversation
        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())[:8]
        
        turn_results = []
        has_error = False
        error_msg = ""
        
        # Phase 1: Execute all API calls and collect responses
        for turn in conversation:
            if should_stop and should_stop():
                break
            turn_num = turn.get("turn", len(turn_results) + 1)
            user_message = turn.get("user", "")
            expected = turn.get("expected", "")
            context = turn.get("retrieval_context", case_data.get("retrieval_context", []))
            
            if not user_message:
                turn_results.append({
                    "turn": turn_num,
                    "user": "",
                    "expected": expected,
                    "actual": "",
                    "error": "Empty user message",
                    "retrieval_context": "",
                    "latency": 0,
                    "ttft": 0
                })
                continue
            
            # Call API with shared session
            turn_thinking = None
            turn_inform_base = None
            turn_raw_data = None
            ttft = 0.0
            turn_latency = 0.0
            
            try:
                start_time = time.time()
                actual_output = _call_chat_with_retry(
                    user_message, 
                    api_name=api_name,
                    user_id=user_id,
                    session_id=session_id
                )
                end_time = time.time()
                turn_latency = end_time - start_time
                
                # Parse thinking process if available
                try:
                    resp_data = json.loads(actual_output)
                    if isinstance(resp_data, dict) and "result" in resp_data:
                        actual_output = resp_data["result"]
                        turn_thinking = resp_data.get("thinking")
                        turn_inform_base = resp_data.get("inform_base")
                        turn_raw_data = resp_data.get("raw")
                        ttft = float(resp_data.get("ttft", 0.0))
                except Exception:
                    pass

            except Exception as e:
                actual_output = f"Error calling API: {str(e)}"
            
            # Check if this is an error response
            is_error = actual_output.startswith("Error") or actual_output.startswith("❌ SERVER DETAIL") or "Error calling API:" in actual_output
            if is_error:
                has_error = True
                error_msg = actual_output
                turn_results.append({
                    "turn": turn_num,
                    "user": user_message,
                    "expected": expected,
                    "actual": actual_output,
                    "error": actual_output,
                    "retrieval_context": ", ".join(context) if isinstance(context, list) else str(context or ""),
                    "thinking": turn_thinking,
                    "inform_base": turn_inform_base,
                    "raw": turn_raw_data,
                    "latency": turn_latency,
                    "ttft": ttft
                })
                break  # Stop on error
            
            turn_results.append({
                "turn": turn_num,
                "user": user_message,
                "expected": expected,
                "actual": actual_output,
                "retrieval_context": ", ".join(context) if isinstance(context, list) else str(context or ""),
                "thinking": turn_thinking,
                "inform_base": turn_inform_base,
                "raw": turn_raw_data,
                "latency": turn_latency,
                "ttft": ttft
            })
        
        num_turns = len(conversation)
        input_text = case_data.get("input")  # First turn input as representative
        
        # Phase 2: If error occurred, return error result without scoring
        if has_error:
            return {
                "case_id": case_data.get("id"),
                "input": input_text,
                "type": "multi_turn",
                "total_turns": num_turns,
                "passed_turns": 0,
                "success_rate": 0,
                "score": 0,
                "reason": f"API 调用失败，跳过评分: {error_msg[:100]}",
                "overall_score": 0,
                "passed": False,
                "latency": sum(t.get("latency", 0) for t in turn_results),
                "ttft": sum(t.get("ttft", 0) for t in turn_results),
                "turns": turn_results,
                "user_id": user_id,
                "session_id": session_id,
                "error": error_msg,
                "category": case_data.get("category"),
                "priority": case_data.get("priority"),
            }
        
        # Phase 3: Build ConversationalTestCase and evaluate with ConversationalGEval
        overall_score = 0.0
        overall_reason = ""
        overall_passed = False
        
        # Check if ConversationalTestCase and Turn are available
        if ConversationalTestCase is not None and Turn is not None and self.conversational_metric is not None:
            try:
                # Build Turn list for ConversationalTestCase
                turns_for_eval = []
                expected_outcomes = []
                for t in turn_results:
                    user_msg = _safe_str(t.get("user"))
                    actual_msg = _safe_str(t.get("actual"))
                    expected_msg = _safe_str(t.get("expected"))
                    if user_msg:
                        turns_for_eval.append(Turn(role="user", content=user_msg))
                    if actual_msg:
                        turns_for_eval.append(Turn(role="assistant", content=actual_msg))
                    if expected_msg:
                        expected_outcomes.append(expected_msg)
                
                # Create ConversationalTestCase
                scenario = _safe_str(case_data.get("description")) or "Multi-turn conversation test"
                expected_outcome = "; ".join(expected_outcomes) if expected_outcomes else "Assistant should provide correct responses"
                
                convo_test_case = ConversationalTestCase(
                    scenario=scenario,
                    expected_outcome=expected_outcome,
                    turns=turns_for_eval
                )
                
                # Evaluate with ConversationalGEval (single LLM call for entire conversation)
                async def eval_conversation():
                    await self.conversational_metric.a_measure(convo_test_case)
                    return self.conversational_metric.score, self.conversational_metric.reason
                
                overall_score, overall_reason = asyncio.run(eval_conversation())
                overall_passed = overall_score >= 0.5
                
            except Exception as e:
                overall_score = 0.0
                overall_reason = f"ConversationalGEval evaluation failed: {str(e)}"
                overall_passed = False
        else:
            # Fallback: ConversationalGEval not available
            overall_reason = "ConversationalGEval not available, scoring skipped"
            overall_passed = False
        
        return {
            "case_id": case_data.get("id"),
            "input": input_text,
            "type": "multi_turn",
            "total_turns": num_turns,
            "passed_turns": num_turns if overall_passed else 0,
            "success_rate": 1.0 if overall_passed else 0.0,
            "score": overall_score,
            "reason": overall_reason,
            "overall_score": overall_score,
            "passed": overall_passed,
            "latency": sum(t.get("latency", 0) for t in turn_results),
            "ttft": sum(t.get("ttft", 0) for t in turn_results),
            "turns": turn_results,
            "user_id": user_id,
            "session_id": session_id,
            "category": case_data.get("category"),
            "priority": case_data.get("priority"),
        }
