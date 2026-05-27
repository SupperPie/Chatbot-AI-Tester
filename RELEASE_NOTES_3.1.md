# Release Notes - Version 3.1

**Release Date:** 2026-05-25  
**Previous Version:** 2.3

## Overview

Version 3.1 is a major feature release that introduces advanced testing capabilities, new API support, and significant improvements to the test execution workflow. This release includes 17 file changes with 822 insertions and 249 deletions.

---

## 🎉 New Features

### 1. Trip Planner API Support
- **Full integration** with Trip Planner API endpoints
- **Automatic extraction** of `data.summary_state.details` from responses
- **Language field support** in extra_args configuration
- **Content-Type detection** for both regular JSON POST and SSE responses
- **Enhanced error reporting** for 422 validation errors

**Usage:**
```json
{
  "trip_planner": {
    "url": "http://example.com/trip-planner",
    "type": "trip_planner",
    "headers": {...},
    "extra_params": {
      "language": "zh-CN"
    }
  }
}
```

### 2. Advanced Search Capabilities
- **Multi-field search**: Keyword search now covers:
  - `input` field
  - `expected_output` field
  - `retrieval_context` field
- **Real-time filtering** in test case management UI
- **Case-insensitive search** with highlight support

### 3. JSONPath Assertion Support
- **Native JSONPath expressions** for complex JSON response validation
- **Integration with jsonpath-ng** library
- **Flexible assertion components** for reusable validation rules
- **Support for nested field extraction**

**Example:**
```python
# Extract hotel names from response
assertion = {
  "type": "jsonpath",
  "expression": "$.data.hotels[*].name",
  "expected": ["Hotel A", "Hotel B"]
}
```

### 4. Multi-turn Dialog Testing
- **Session management** with automatic user_id and session_id handling
- **Context preservation** across conversation turns
- **Turn-by-turn validation** with individual assertions
- **Proper thread_id handling** for different API types

### 5. Range Execution
- **Execute by ID range**: Run tests from specific start ID to end ID
- **Flexible selection**: Combine with other filters (tags, categories)
- **Progress tracking**: Real-time progress display for range execution

### 6. Tag-based Execution
- **Filter by tags**: Execute only test cases with selected tags
- **Multi-tag support**: AND/OR logic for complex tag queries
- **Dynamic tag management**: Create and assign tags on-the-fly

### 7. F1 Score Preparation
- **New `expected_result` field** added to test_case model
- **Support for negative samples**: Mark test cases as expected "pass" or "fail"
- **Future F1 calculation**: Foundation for precision, recall, and F1 metrics
  - TP: expected=pass, actual=pass
  - FP: expected=fail, actual=pass
  - TN: expected=fail, actual=fail
  - FN: expected=pass, actual=fail

---

## 🐛 Bug Fixes

### Hotel API
- **Fixed 422 validation error**: Removed `thread_id` from payload (not accepted by server)
- **Fixed missing_fields format**: Ensure it's always an array, not object

### Entitlements API (权益中信)
- **Updated API URL**: Changed from `172.21.12.136` to `192.168.22.252`
- **Network connectivity**: Resolved "Network is unreachable" error
- **user_equity_list extraction**: Properly extract to `inform_base` field

### Trip Planner API
- **Handle None summary_state**: Safe extraction when summary_state is None
- **Language field**: Added to extra_args for i18n support
- **Content-Type detection**: Properly handle both JSON and SSE responses
- **422 error reporting**: Improved error messages for validation failures

### General Fixes
- **Request params JSON parsing**: Handle None cell values (avoid `str(None)='None'`)
- **Tag filter**: Fix missing rows when tags stored as string instead of list in DataFrame
- **Test report**: Force job status update for stuck running jobs

---

## 🚀 Improvements

### Test Engine Refactoring
- **494 lines changed** in test_engine.py
- **Better code structure**: Clearer separation of concerns
- **Enhanced error handling**: More robust exception management
- **Performance optimization**: Reduced unnecessary API calls

### Test Case Service
- **78 lines improved** with better query optimization
- **Category management**: Enhanced directory tree operations
- **Batch operations**: Improved bulk import/export

### UI Enhancements
- **Test Cases Page** (189+ lines): Better layout, responsive design
- **Test Report Page** (81+ lines): Enhanced result display, manual review support
- **Settings Page** (24+ lines): Improved API configuration UI
- **Sidebar** (10+ lines): Better navigation and status indicators

### Dependencies
- **jsonpath-ng**: Added for JSONPath assertion support
- **streamlit**: Fixed version requirement (>=1.35.0 instead of non-existent >=1.50.0)
- **Python 3.11**: Full compatibility with latest Python version

---

## 🔧 Technical Details

### Database Schema Updates
```sql
-- Added to test_cases table
ALTER TABLE test_cases ADD COLUMN expected_result VARCHAR(20) DEFAULT 'pass';
```

### API Configuration Changes
- **Trip Planner**: New API type with specialized handling
- **Entitlements**: URL update required in `api_config.json`

### Breaking Changes
None. This release is fully backward compatible with version 2.3.

---

## 📊 Statistics

- **Total Files Changed**: 17
- **Lines Added**: 822
- **Lines Removed**: 249
- **Net Change**: +573 lines
- **Commits since 2.3**: 8

---

## 🛠️ Upgrade Instructions

### 1. Update Dependencies
```bash
pip install -r requirements.txt
```

### 2. Apply Database Migration
```bash
# Manually add expected_result column if using existing database
ALTER TABLE test_cases ADD COLUMN expected_result VARCHAR(20) DEFAULT 'pass';
```

### 3. Update API Configuration
If using Entitlements API (权益中信), update URL in `data/api_config.json`:
```json
{
  "权益(中信)": {
    "url": "http://192.168.22.252:13579/stream"
  }
}
```

### 4. Test New Features
- Try Trip Planner API with sample test cases
- Experiment with range execution and tag filtering
- Verify JSONPath assertions work as expected

---

## 🔮 What's Next (Version 3.2)

Planned features for the next release:
- **F1 Score Calculation**: Full implementation with TP/FP/TN/FN metrics
- **Advanced Metrics Dashboard**: Precision, Recall, F1 score visualization
- **Test Case Templates**: Reusable templates for common scenarios
- **API Mock Server**: Built-in mock server for offline testing
- **Performance Benchmarking**: Response time tracking and alerting

---

## 📝 Contributors

This release includes contributions and fixes from:
- Internal testing team feedback
- API integration improvements
- User experience enhancements

---

## 🙏 Acknowledgments

Special thanks to all users who reported issues and provided valuable feedback during the 2.3 release cycle.

---

For detailed commit history, see: `git log release/2.3..release/3.1`
