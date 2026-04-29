-- Active: 1776665709024@@192.168.26.241@5432@dp_testmate@ai_chatbot_tester
-- Active: 1776665709024@@192.168.26.241@5432@dp_testmate
-- =============================================
-- DeepEval 测试管理系统 - 完整建表脚本
-- 请在 PostgreSQL 中执行此脚本
-- =============================================

-- 1. 目录分类表（支持3级树形结构）
CREATE TABLE IF NOT EXISTS categories (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id VARCHAR(50) REFERENCES categories(id) ON DELETE CASCADE,
    path VARCHAR(500) NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_level CHECK (level >= 1 AND level <= 3)
);

CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_categories_level ON categories(level);
CREATE INDEX IF NOT EXISTS idx_categories_path ON categories(path);

-- 创建根目录（系统保留）
INSERT INTO categories (id, name, parent_id, path, level, sort_order)
VALUES ('root', '全部用例', NULL, '全部用例', 1, 0)
ON CONFLICT (id) DO NOTHING;

-- 2. 预定义标签表
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 测试用例表（复合主键：id + turn_index，支持多轮对话共用同一 ID）
CREATE TABLE IF NOT EXISTS test_cases (
    id VARCHAR(50) NOT NULL,
    type VARCHAR(20) DEFAULT 'single',
    input TEXT NOT NULL,
    expected_output TEXT,
    retrieval_context TEXT,
    description TEXT,
    turn_index INTEGER NOT NULL DEFAULT 1,
    validation TEXT,
    overall_criteria TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    category_id VARCHAR(50) REFERENCES categories(id) ON DELETE SET NULL DEFAULT 'root',
    tags JSONB DEFAULT '[]',
    PRIMARY KEY (id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_test_cases_category ON test_cases(category_id);
CREATE INDEX IF NOT EXISTS idx_test_cases_type ON test_cases(type);

-- 4. 测试用例-标签关联表（注意：该表未被应用层使用，tags 存储在 test_cases.tags JSONB 列中）
CREATE TABLE IF NOT EXISTS test_case_tags (
    test_case_id VARCHAR(50),
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (test_case_id, tag_id)
);

-- 5. 测试历史表（测试报告）
CREATE TABLE IF NOT EXISTS test_history (
    id VARCHAR(50) PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    api_name VARCHAR(100),
    total INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    started_count INTEGER DEFAULT 0,
    source VARCHAR(20) DEFAULT 'local',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_test_history_status ON test_history(status);
CREATE INDEX IF NOT EXISTS idx_test_history_timestamp ON test_history(timestamp);

-- 6. 测试结果表（与 test_history 关联）
CREATE TABLE IF NOT EXISTS test_results (
    id SERIAL PRIMARY KEY,
    history_id VARCHAR(50) REFERENCES test_history(id) ON DELETE CASCADE,
    case_id VARCHAR(50),
    input TEXT,
    actual_output TEXT,
    expected_output TEXT,
    retrieval_context TEXT,
    score FLOAT,
    reason TEXT,
    faithfulness_score FLOAT,
    faithfulness_reason TEXT,
    passed BOOLEAN DEFAULT FALSE,
    thinking TEXT,
    inform_base TEXT,
    raw TEXT,
    latency FLOAT,
    ttft FLOAT,
    type VARCHAR(20),
    total_turns INTEGER,
    passed_turns INTEGER,
    success_rate FLOAT,
    overall_score FLOAT,
    overall_passed BOOLEAN,
    turns JSONB,
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_test_results_history ON test_results(history_id);
CREATE INDEX IF NOT EXISTS idx_test_results_case ON test_results(case_id);

-- 7. 盲测评审表
CREATE TABLE IF NOT EXISTS blind_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. 盲测评审项目表
CREATE TABLE IF NOT EXISTS blind_review_items (
    id SERIAL PRIMARY KEY,
    review_id UUID REFERENCES blind_reviews(id) ON DELETE CASCADE,
    input TEXT,
    options JSONB,
    votes JSONB DEFAULT '{"A": 0, "B": 0}'
);

CREATE INDEX IF NOT EXISTS idx_blind_review_items_review ON blind_review_items(review_id);

-- 9. API 配置表
CREATE TABLE IF NOT EXISTS api_configs (
    name VARCHAR(100) PRIMARY KEY,
    url TEXT NOT NULL,
    description TEXT,
    type VARCHAR(50),
    token TEXT,
    request_params JSONB DEFAULT '{}'
);

-- 10. 草稿批次管理表（Tester 页面大量生成时用）
CREATE TABLE IF NOT EXISTS draft_batches (
    id VARCHAR(50) PRIMARY KEY,
    total_count INTEGER DEFAULT 0,
    current_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'generating',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 11. 测试用例草稿表
CREATE TABLE IF NOT EXISTS test_case_drafts (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(50) REFERENCES draft_batches(id) ON DELETE CASCADE,
    case_data JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_drafts_batch_id ON test_case_drafts(batch_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON test_case_drafts(status);

-- 12. 多媒体附件表（预留，支持图片、音频）
CREATE TABLE IF NOT EXISTS attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    mime_type VARCHAR(100),
    file_size INTEGER,
    storage_path TEXT NOT NULL,
    thumbnail_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- 执行完成后验证：
-- SELECT table_name FROM information_schema.tables 
-- WHERE table_schema = 'public';
-- =============================================
