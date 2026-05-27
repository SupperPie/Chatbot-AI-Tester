import streamlit as st
import json
import logging
from app.services.assertion_service import AssertionService

logger = logging.getLogger(__name__)


def _parse_response_json(text: str):
    """
    解析 API 响应 JSON，支持两种格式：
    1. 单个 JSON 对象
    2. NDJSON（每行一个 JSON，SSE 流式响应）
       - 优先返回最后一条 type=done 的消息
       - 如果没有 done，返回最后一条可解析的 JSON
    返回 (parsed_dict, error_msg)，成功时 error_msg 为 None。
    """
    text = text.strip()
    if not text:
        return None, "请粘贴 JSON"

    # 尝试单个 JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, None
    except json.JSONDecodeError:
        pass

    # 尝试 NDJSON（多行）
    lines = text.splitlines()
    parsed_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                parsed_lines.append(obj)
        except json.JSONDecodeError:
            continue

    if not parsed_lines:
        return None, "JSON 格式错误（不是有效的单个 JSON 也不是有效的 NDJSON）"

    # 优先取 type=done 的行
    done_msgs = [p for p in parsed_lines if p.get("type") == "done"]
    if done_msgs:
        return done_msgs[-1], None

    # 其次取最后一条 message
    msg_msgs = [p for p in parsed_lines if p.get("type") == "message"]
    if msg_msgs:
        return msg_msgs[-1], None

    # 最后返回最后一行
    return parsed_lines[-1], None


def render_assertions_page():
    """断言组件库管理页面"""
    st.title("🧩 断言组件库")

    # Tab 切换
    tab_list, tab_create = st.tabs(["组件列表", "组件生成"])

    with tab_list:
        _render_component_list()

    with tab_create:
        _render_component_create()


# ═══════════════════════════════════════════════════════
# Tab 1: 组件列表
# ═══════════════════════════════════════════════════════

def _render_component_list():
    """渲染组件列表，含筛选、卡片展示、测试、编辑、删除"""
    service = AssertionService()

    # ─── 筛选栏 ───
    col1, col2, col3, col4 = st.columns([2, 2, 3, 2])
    with col1:
        category_filter = st.selectbox(
            "大类", ["全部", "field", "structure", "status_code", "composite"],
            key="assert_filter_category"
        )
    with col2:
        all_tags = service.get_all_tags()
        tag_filter = st.selectbox(
            "标签", ["全部"] + all_tags,
            key="assert_filter_tag"
        )
    with col3:
        keyword = st.text_input("搜索组件名称", key="assert_filter_keyword", placeholder="输入关键词...")
    with col4:
        st.write("")  # spacer
        st.write("")
        refresh = st.button("🔄 刷新", key="assert_refresh")

    # ─── 查询 ───
    cat = category_filter if category_filter != "全部" else None
    tag = tag_filter if tag_filter != "全部" else None
    kw = keyword.strip() if keyword else None
    components = service.search(keyword=kw, category=cat, tag=tag)

    st.caption(f"共 {len(components)} 个组件")

    if not components:
        st.info("暂无组件，请在「组件生成」Tab 中创建。")
        return

    # ─── 卡片网格 ───
    cols_per_row = 2
    for i in range(0, len(components), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(components):
                break
            comp = components[idx]
            with col:
                _render_component_card(comp, service)


def _render_component_card(comp, service: AssertionService):
    """渲染单个组件卡片"""
    with st.container(border=True):
        # Header: ID + badges
        header_cols = st.columns([3, 2])
        with header_cols[0]:
            st.markdown(f"**{comp.name}**")
        with header_cols[1]:
            badge_color = {
                "field": "blue", "structure": "green",
                "status_code": "red", "composite": "violet"
            }.get(comp.category, "gray")
            st.markdown(
                f"<span style='font-size:0.75rem;'>`{comp.id}` "
                f"<span style='background-color:{'#e3f2fd' if comp.category=='field' else '#e8f5e9' if comp.category=='structure' else '#fce4ec' if comp.category=='status_code' else '#ede7f6'};padding:2px 6px;border-radius:10px;font-size:0.7rem;'>{comp.category}</span> "
                f"<span style='background-color:#f5f5f5;padding:2px 6px;border-radius:10px;font-size:0.7rem;'>{comp.condition}</span></span>",
                unsafe_allow_html=True
            )

        # Params / Composite checks
        config = comp.config or {}
        if comp.category == "composite":
            checks = config.get("checks", [])
            st.caption(f"包含 {len(checks)} 项检查")
            for ck in checks[:4]:
                if "ref" in ck:
                    st.markdown(f"&nbsp;&nbsp;🔗 ref: `{ck['ref']}`", unsafe_allow_html=True)
                else:
                    st.markdown(
                        f"&nbsp;&nbsp;▸ {ck.get('category','')}/{ck.get('condition','')}",
                        unsafe_allow_html=True
                    )
            if len(checks) > 4:
                st.caption(f"  ...还有 {len(checks)-4} 项")
        else:
            params = config.get("params", {})
            deferred = config.get("deferred_params", [])
            for k, v in params.items():
                mode = "活参数" if k in deferred else "固定"
                display_val = f"`{json.dumps(v, ensure_ascii=False)}`" if mode == "固定" else "_关联时填写_"
                st.markdown(f"&nbsp;&nbsp;{k}: {display_val} ({mode})", unsafe_allow_html=True)

        # Tags
        if comp.tags:
            st.markdown(" ".join([f"`{t}`" for t in comp.tags]))

        # Footer: actions
        ref_count = service.get_reference_count(comp.id)
        st.caption(f"引用: {ref_count} 个用例")

        btn_cols = st.columns(3)
        with btn_cols[0]:
            if st.button("✏️ 编辑", key=f"edit_{comp.id}"):
                st.session_state[f"editing_{comp.id}"] = True
                st.rerun()
        with btn_cols[1]:
            if st.button("🧪 测试", key=f"test_{comp.id}"):
                st.session_state[f"testing_{comp.id}"] = not st.session_state.get(f"testing_{comp.id}", False)
                st.rerun()
        with btn_cols[2]:
            # 二次确认删除
            confirm_key = f"confirm_del_{comp.id}"
            if st.session_state.get(confirm_key, False):
                st.warning(f"确定删除 `{comp.id}`？")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("确认删除", key=f"yes_del_{comp.id}", type="primary"):
                        service.delete(comp.id)
                        st.session_state[confirm_key] = False
                        st.success(f"已删除 {comp.id}")
                        st.rerun()
                with col_no:
                    if st.button("取消", key=f"no_del_{comp.id}"):
                        st.session_state[confirm_key] = False
                        st.rerun()
            else:
                if st.button("🗑️ 删除", key=f"del_{comp.id}"):
                    st.session_state[confirm_key] = True
                    st.rerun()

        # ─── 编辑面板 ───
        if st.session_state.get(f"editing_{comp.id}", False):
            _render_edit_panel(comp, service)

        # ─── 测试面板 ───
        if st.session_state.get(f"testing_{comp.id}", False):
            _render_test_panel(comp)


def _render_edit_panel(comp, service: AssertionService):
    """组件编辑面板"""
    with st.expander("编辑组件", expanded=True):
        new_name = st.text_input("名称", value=comp.name, key=f"editname_{comp.id}")
        new_tags = st.text_input("标签 (逗号分隔)", value=", ".join(comp.tags or []), key=f"edittags_{comp.id}")
        new_config = st.text_area("Config (JSON)", value=json.dumps(comp.config, ensure_ascii=False, indent=2), height=150, key=f"editcfg_{comp.id}")

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("保存", key=f"save_{comp.id}"):
                try:
                    parsed_config = json.loads(new_config)
                    tags_list = [t.strip() for t in new_tags.split(",") if t.strip()]
                    service.update(comp.id, {
                        "name": new_name,
                        "tags": tags_list,
                        "config": parsed_config,
                    })
                    st.session_state[f"editing_{comp.id}"] = False
                    st.success("已保存")
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("Config JSON 格式错误")
        with col_cancel:
            if st.button("取消", key=f"cancel_{comp.id}"):
                st.session_state[f"editing_{comp.id}"] = False
                st.rerun()


def _render_test_panel(comp):
    """本地验证面板"""
    st.markdown("---")
    st.markdown("**🧪 本地验证** (不调用真实 API)")
    test_json = st.text_area(
        "粘贴 API 响应 JSON:",
        height=80,
        key=f"testjson_{comp.id}",
        placeholder='{"type":"token","lob":"dc","content":"...","data":{}}'
    )

    # 活参数填写
    config = comp.config or {}
    deferred = config.get("deferred_params", [])
    override_params = {}
    if deferred:
        st.caption("填写活参数:")
        for param_name in deferred:
            val = st.text_input(f"{param_name} =", key=f"deferred_{comp.id}_{param_name}")
            if val:
                override_params[param_name] = val

    if st.button("执行验证 ▶", key=f"runtest_{comp.id}"):
        response, err = _parse_response_json(test_json)
        if err:
            st.error(err)
            return

        from app.validators.engine import AssertionEngine
        engine = AssertionEngine()
        comp_data = {
            "id": comp.id,
            "name": comp.name,
            "category": comp.category,
            "condition": comp.condition,
            "config": config,
        }
        results = engine.run_local(response, comp_data, override_params)
        for r in results:
            if r.passed:
                st.success(f"✅ PASS — {r.message}")
            else:
                st.error(f"❌ FAIL — {r.message}")


# ═══════════════════════════════════════════════════════
# Tab 2: 组件生成 (AI + 手动)
# ═══════════════════════════════════════════════════════

def _render_component_create():
    """组件生成 Tab: AI 生成 + 手动创建"""

    # ===== AI 一键生成 =====
    st.subheader("🤖 AI 一键生成")
    st.caption("粘贴 API 响应样本 + 自然语言描述断言需求 → AI 自动生成断言组件定义。")

    col_json, col_desc = st.columns(2)
    with col_json:
        ai_json = st.text_area(
            "API 响应样本 (粘贴 JSON)",
            height=140,
            key="ai_gen_json",
            placeholder='{"type":"token","lob":"dc","content":"您好","data":{"flights":[...]}}'
        )
    with col_desc:
        ai_desc = st.text_area(
            "断言需求 (自然语言描述)",
            height=140,
            key="ai_gen_desc",
            placeholder="检查顶层必须包含 type、lob、content、data 四个字段，lob 等于 dc，content 不为空..."
        )

    if st.button("✨ 一键生成", key="ai_generate_btn"):
        if not ai_json.strip() or not ai_desc.strip():
            st.warning("请填写 JSON 样本和断言需求描述")
        else:
            _run_ai_generation(ai_json, ai_desc)

    # 保存成功提示
    if st.session_state.get("ai_save_success"):
        st.success(st.session_state.ai_save_success)
        del st.session_state["ai_save_success"]

    # 展示 AI 生成结果（如果有）
    if "ai_gen_results" in st.session_state and st.session_state.ai_gen_results:
        _render_ai_results()

    # ===== 分割线 =====
    st.divider()

    # ===== 手动创建 =====
    st.subheader("✏️ 手动创建组件")
    _render_manual_create()


def _run_ai_generation(sample_json: str, description: str):
    """调用 LLM 生成断言组件定义"""
    import os
    try:
        import openai
        client = openai.OpenAI(
            base_url=os.getenv("COMPATIBLE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            api_key=os.getenv("COMPATIBLE_API_KEY"),
        )

        prompt = f"""你是一个 API 测试断言生成器。根据用户的 JSON 样本和自然语言描述，生成断言组件定义列表。

【重要】字段路径使用 JSONPath 标准语法：
- 绝对路径: `$.field.nested` 或简写 `field.nested`
- 递归搜索: `$..fieldName` (在任意层级查找)
- 数组索引: `$.array[0].field`
- 通配符: `$.array[*].field`

【重要】scope 参数（可选）用于指定 SSE 消息类型：
- scope: "" (空) → 使用合并后的完整响应，JSONPath 递归搜索
- scope: "done" → 只在 type=done 的消息中查找
- scope: "token" → 只在 token 消息中查找
- scope: "message" / "content" → 对应消息类型
- scope 可自定义其他值

每个断言组件必须包含:
- name: 组件名称（简洁中文）
- category: "field" | "structure" | "status_code"
- condition: 对应 category 的条件类型
  - field: equals / not_equals / contains / matches / in / not_empty / type / gt / gte / lt / lte / length
  - structure: path_exists / required_fields / field_count / array_not_empty / nested_structure
  - status_code: equals / in_range / not_equals
- params: 参数对象，必须包含:
  - field: JSONPath 路径（如 `$.data.bundle_list[0].bundle_name` 或简写 `data.bundle_list[0].bundle_name`）
  - expected: 期望值（field 类型）或字段列表（structure 类型）
  - scope: 消息类型过滤（可选，默认空字符串）
- param_mode: 每个参数是 "preset"(固定) 还是 "deferred"(关联时填写)

JSON 样本:
```json
{sample_json}
```

用户需求: {description}

请严格按以下 JSON 格式输出（只输出 JSON 数组，不要其他文字）:
```json
[
  {{"name": "...", "category": "...", "condition": "...", "params": {{"field": "$.path", "expected": "value", "scope": "done"}}, "param_mode": {{"field": "preset|deferred", "expected": "preset|deferred", "scope": "preset"}}}}
]
```"""

        with st.spinner("AI 生成中..."):
            response = client.chat.completions.create(
                model=os.getenv("COMPATIBLE_MODEL", "qwen3-max"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            content = response.choices[0].message.content.strip()

            # 提取 JSON
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            else:
                # try raw array
                arr_match = re.search(r'\[.*\]', content, re.DOTALL)
                if arr_match:
                    content = arr_match.group(0)

            generated = json.loads(content)
            if not isinstance(generated, list):
                generated = [generated]

            # 去重匹配
            service = AssertionService()
            results_with_dedup = []
            for item in generated:
                cat = item.get("category", "field")
                cond = item.get("condition", "equals")
                params = item.get("params", {})
                param_mode = item.get("param_mode", {})

                # 提取 preset 参数用于匹配
                preset_params = {k: v for k, v in params.items() if param_mode.get(k, "preset") == "preset"}

                exact_match = service.find_matching_component(cat, cond, preset_params)
                similar = service.find_similar_components(cat, cond) if not exact_match else []

                results_with_dedup.append({
                    "item": item,
                    "exact_match": {"id": exact_match.id, "name": exact_match.name} if exact_match else None,
                    "similar": [{"id": s.id, "name": s.name} for s in similar[:3]] if similar else [],
                })

            st.session_state.ai_gen_results = results_with_dedup
            st.session_state.ai_gen_json_sample = sample_json
            st.rerun()

    except Exception as e:
        st.error(f"AI 生成失败: {e}")
        logger.exception("AI generation failed")


def _render_ai_results():
    """渲染 AI 生成结果（含去重状态），支持勾选"""
    results = st.session_state.ai_gen_results
    service = AssertionService()

    new_count = sum(1 for r in results if not r["exact_match"])
    st.markdown(f"**生成了 {len(results)} 项检查: {new_count} 项新增, {len(results) - new_count} 项已存在**")

    # 初始化选中状态
    if "ai_gen_selected" not in st.session_state or len(st.session_state.ai_gen_selected) != len(results):
        # 默认选中所有新增项
        st.session_state.ai_gen_selected = [not r["exact_match"] for r in results]

    for i, r in enumerate(results):
        item = r["item"]
        match = r["exact_match"]

        with st.container(border=True):
            col_check, col_content = st.columns([0.5, 9.5])
            with col_check:
                checked = st.checkbox("", value=st.session_state.ai_gen_selected[i], key=f"ai_sel_{i}", label_visibility="collapsed")
                st.session_state.ai_gen_selected[i] = checked
            with col_content:
                if match:
                    st.markdown(f"**{i+1}. {item['name']}** ✅ 已存在 → 复用 `{match['id']}`")
                    st.caption(f"{item['category']} / {item['condition']} | 匹配: \"{match['name']}\"")
                else:
                    st.markdown(f"**{i+1}. {item['name']}** ⭐ 新增")
                    st.caption(f"{item['category']} / {item['condition']} | params: {json.dumps(item.get('params',{}), ensure_ascii=False)}")
                    if r["similar"]:
                        sim_text = ", ".join([f"`{s['id']}`" for s in r["similar"]])
                        st.caption(f"近似组件: {sim_text}")

    # 统计选中数量
    selected_indices = [i for i, s in enumerate(st.session_state.ai_gen_selected) if s]
    selected_new = [i for i in selected_indices if not results[i]["exact_match"]]

    # 保存操作
    st.markdown("---")
    col_a, col_b, col_c = st.columns([2, 2, 1])
    with col_a:
        if selected_new:
            if st.button(f"💾 保存选中新增项 ({len(selected_new)}个)", key="ai_save_new_only"):
                saved = 0
                for i in selected_new:
                    _save_ai_generated_component(results[i]["item"])
                    saved += 1
                st.session_state.ai_gen_results = None
                st.session_state.pop("ai_gen_selected", None)
                st.session_state.ai_save_success = f"已保存 {saved} 个新组件到组件库"
                st.rerun()
        else:
            st.caption("未选中任何新增项")
    with col_b:
        if selected_indices:
            if st.button(f"🧩 选中项打包为组合 ({len(selected_indices)}个)", key="ai_save_composite"):
                selected_results = [results[i] for i in selected_indices]
                _save_as_composite(selected_results, service)
        else:
            st.caption("请勾选要打包的项")
    with col_c:
        if st.button("🗑️ 丢弃", key="ai_discard"):
            st.session_state.ai_gen_results = None
            st.session_state.pop("ai_gen_selected", None)
            st.rerun()

    # 本地验证
    st.markdown("---")
    if st.button("▶ 本地验证全部", key="ai_local_validate"):
        sample = st.session_state.get("ai_gen_json_sample", "")
        if sample:
            response, err = _parse_response_json(sample)
            if err:
                st.error(err)
            else:
                from app.validators.engine import AssertionEngine
                engine = AssertionEngine()
                all_pass = True
                for i, r in enumerate(results):
                    item = r["item"]
                    comp_data = {
                        "id": f"gen_{i}",
                        "name": item["name"],
                        "category": item["category"],
                        "condition": item["condition"],
                        "config": {"params": item.get("params", {})},
                    }
                    res_list = engine.run_local(response, comp_data)
                    for res in res_list:
                        if res.passed:
                            st.success(f"✅ {i+1}. {item['name']} — PASS: {res.message}")
                        else:
                            st.error(f"❌ {i+1}. {item['name']} — FAIL: {res.message}")
                            all_pass = False
                if all_pass:
                    st.success(f"全部通过 ({len(results)}/{len(results)})")


def _save_ai_generated_component(item: dict):
    """保存 AI 生成的单个组件"""
    service = AssertionService()
    param_mode = item.get("param_mode", {})
    deferred_params = [k for k, v in param_mode.items() if v == "deferred"]

    service.create({
        "name": item["name"],
        "category": item["category"],
        "condition": item["condition"],
        "config": {
            "params": item.get("params", {}),
            "deferred_params": deferred_params,
        },
        "tags": item.get("tags", []),
    })


def _save_as_composite(results: list, service: AssertionService):
    """将所有生成结果打包为一个 composite 组件"""
    checks = []
    for r in results:
        if r["exact_match"]:
            checks.append({"ref": r["exact_match"]["id"]})
        else:
            item = r["item"]
            checks.append({
                "category": item["category"],
                "condition": item["condition"],
                "params": item.get("params", {}),
            })

    service.create({
        "name": "AI 生成组合断言",
        "category": "composite",
        "condition": "all_pass",
        "config": {"checks": checks},
        "tags": ["AI生成"],
    })
    st.session_state.ai_gen_results = None
    st.session_state.ai_save_success = "已保存为组合组件 (composite)"
    st.rerun()


# ═══════════════════════════════════════════════════════
# 手动创建
# ═══════════════════════════════════════════════════════

# 各 category 对应的 condition 列表
CATEGORY_CONDITIONS = {
    "field": ["equals", "not_equals", "contains", "matches", "in", "not_empty", "type", "gt", "gte", "lt", "lte", "length"],
    "structure": ["path_exists", "required_fields", "field_count", "array_not_empty", "nested_structure"],
    "status_code": ["equals", "in_range", "not_equals"],
    "composite": ["all_pass", "any_pass"],
}

# 各 condition 需要的参数
CONDITION_PARAMS = {
    "equals": ["field", "expected"],
    "not_equals": ["field", "expected"],
    "contains": ["field", "expected"],
    "matches": ["field", "pattern"],
    "in": ["field", "values"],
    "not_empty": ["field"],
    "type": ["field", "expected_type"],
    "gt": ["field", "value"],
    "gte": ["field", "value"],
    "lt": ["field", "value"],
    "lte": ["field", "value"],
    "length": ["field", "operator", "value"],
    "path_exists": ["path"],
    "required_fields": ["path", "fields"],
    "field_count": ["path", "operator", "value"],
    "array_not_empty": ["path"],
    "nested_structure": ["path", "fields"],
    "in_range": ["min", "max"],
    "all_pass": [],
    "any_pass": [],
}


def _render_manual_create():
    """手动创建组件表单"""
    col_name, col_tags = st.columns(2)
    with col_name:
        name = st.text_input("组件名称", key="manual_name", placeholder="如: lob 值检查、顶层结构验证")
    with col_tags:
        tags_str = st.text_input("标签 (逗号分隔)", key="manual_tags", placeholder="通用, 航班")

    # 第一步：选择大类
    st.markdown("**第一步: 选择断言大类**")
    category = st.radio(
        "大类", ["field", "structure", "status_code", "composite"],
        horizontal=True, key="manual_category",
        format_func=lambda x: {"field": "📋 field (字段值检查)", "structure": "🏗️ structure (结构检查)",
                               "status_code": "🔢 status_code (状态码)", "composite": "🧩 composite (组合断言)"}[x]
    )

    # 第二步：选择条件
    st.markdown("**第二步: 选择判断条件**")
    conditions = CATEGORY_CONDITIONS.get(category, [])
    condition = st.selectbox("条件", conditions, key="manual_condition")

    # 第三步：参数配置
    st.markdown("**第三步: 参数配置**")

    if category == "composite":
        st.info("组合组件请通过 AI 生成后「打包为组合组件」创建，或直接编辑 config JSON。")
        config_json = st.text_area(
            "Config JSON (composite checks)",
            height=120,
            key="manual_composite_config",
            placeholder='{"checks": [{"ref": "AC001"}, {"category": "field", "condition": "equals", "params": {"field": "lob", "expected": "dc"}}]}'
        )
    else:
        param_names = CONDITION_PARAMS.get(condition, [])
        params = {}
        deferred_params = []

        # scope 字段（适用于所有 atomic 组件，过滤 SSE 消息类型）
        st.markdown("**Scope (可选)** - 过滤 SSE 消息类型，留空则递归搜索整个响应")
        scope_choice = st.selectbox(
            "Scope",
            ["", "done", "token", "message", "content", "自定义"],
            key="manual_scope_choice",
            help="done: 取 type=done 消息 | token: token 流 | message/content: 对应消息类型 | 自定义: 输入其他 type 值"
        )
        if scope_choice == "自定义":
            scope_value = st.text_input("自定义 scope 值", key="manual_scope_custom")
        else:
            scope_value = scope_choice
        if scope_value:
            params["scope"] = scope_value

        for param_name in param_names:
            st.markdown(f"**参数: `{param_name}`**")
            col_mode, col_val = st.columns([1, 3])
            with col_mode:
                mode = st.radio(
                    "模式", ["预设值(固定)", "关联时填写(活参数)"],
                    key=f"manual_mode_{param_name}", horizontal=True
                )
            with col_val:
                if mode == "预设值(固定)":
                    val = st.text_input(f"{param_name} 值", key=f"manual_val_{param_name}")
                    if val:
                        # 尝试解析为 JSON 值
                        try:
                            params[param_name] = json.loads(val)
                        except (json.JSONDecodeError, ValueError):
                            params[param_name] = val
                else:
                    deferred_params.append(param_name)
                    st.caption(f"_{param_name} 将在关联测试用例时填写_")

    # 保存按钮
    st.markdown("---")
    col_save, col_validate = st.columns(2)
    with col_save:
        if st.button("💾 保存组件", key="manual_save"):
            if not name.strip():
                st.warning("请输入组件名称")
                return

            service = AssertionService()
            tags_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

            if category == "composite":
                try:
                    config = json.loads(config_json) if config_json else {"checks": []}
                except json.JSONDecodeError:
                    st.error("Config JSON 格式错误")
                    return
            else:
                config = {"params": params, "deferred_params": deferred_params}

            service.create({
                "name": name.strip(),
                "category": category,
                "condition": condition,
                "config": config,
                "tags": tags_list,
            })
            st.success(f"组件 '{name}' 已保存!")
            st.rerun()

    with col_validate:
        if st.button("▶ 本地验证", key="manual_validate"):
            st.session_state["show_manual_test"] = True
            st.rerun()

    # 本地验证区域
    if st.session_state.get("show_manual_test", False):
        st.markdown("---")
        st.markdown("**本地验证** (不调用真实 API)")
        test_json = st.text_area("粘贴 JSON:", height=80, key="manual_test_json")

        # 活参数填写
        if category != "composite" and deferred_params:
            st.caption("填写活参数:")
            test_override = {}
            for p in deferred_params:
                v = st.text_input(f"{p} =", key=f"manual_test_deferred_{p}")
                if v:
                    try:
                        test_override[p] = json.loads(v)
                    except (json.JSONDecodeError, ValueError):
                        test_override[p] = v
        else:
            test_override = {}

        if st.button("执行 ▶", key="manual_run_test"):
            response, err = _parse_response_json(test_json)
            if err:
                st.error(err)
            else:
                from app.validators.engine import AssertionEngine
                engine = AssertionEngine()

                if category == "composite":
                    try:
                        config = json.loads(config_json) if config_json else {"checks": []}
                    except:
                        config = {"checks": []}
                else:
                    all_params = dict(params)
                    all_params.update(test_override)
                    config = {"params": all_params}

                comp_data = {
                    "id": "preview",
                    "name": name or "preview",
                    "category": category,
                    "condition": condition,
                    "config": config,
                }
                res_list = engine.run_local(response, comp_data)
                for r in res_list:
                    if r.passed:
                        st.success(f"✅ PASS — {r.message}")
                    else:
                        st.error(f"❌ FAIL — {r.message}")
