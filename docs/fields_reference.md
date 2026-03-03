# Test Data Fields Reference

This document explains the key fields used in the Import Template and Test Cases.

## 0. ID (Feature)
- **Description**: Unique identifier for the test case (e.g., `TC0001`).
- **Usage**:
    - **New Cases**: Leave empty. The system will auto-generate it.
    - **Update Existing**: Fill in the existing ID to update that specific case (requires "Update existing cases by ID" checked during import).

## 1. Validation
- **Description**: Defines how to judge if the AI's answer is correct for a specific turn.
- **Usage**: JSON string defining the validation logic.
- **Types**:
    - **Semantic (Default)**: Uses an LLM to judge meaning similarity.
        - `{'type': 'semantic', 'threshold': 0.7}`
    - **Contains (Keyword)**: Checks if specific keywords are present.
        - `{'type': 'contains', 'keywords': ['success', '200 OK'], 'threshold': 0.5}`
        - Threshold is the percentage of keywords that must verify.
    - **Exact**: Strict string equality.
        - `{'type': 'exact'}`

## 2. Overall_Criteria (Multi-turn only)
- **Description**: Defines the success criteria for an entire multi-turn conversation session.
- **Usage**: JSON string in the **first row** of a multi-turn case.
- **Fields**:
    - `min_success_rate`: Percentage of turns that must pass (0.0 to 1.0).
    - `must_complete_all_turns`: If `true`, the test fails if the conversation stops early or errors out.
- **Example**: `{'min_success_rate': 0.8, 'must_complete_all_turns': true}` (Means 80% of questions must be answered correctly).

## 3. Retrieval_Context
- **Description**: The background knowledge or reference text that the AI should use to answer the question (RAG context).
- **Usage**:
    - If your bot uses RAG (Retrieval Augmented Generation), paste the retrieved chunks here.
    - Used by the **Faithfulness** metric to check if the AI's answer strictly follows this context.
- **Format**: JSON list of strings.
    - Example: `['The event starts at 10 AM.', 'Location is Room A.']`
    - CSV Example: `"['The event starts at 10 AM.']"`
