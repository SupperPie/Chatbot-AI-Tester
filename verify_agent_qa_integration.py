#!/usr/bin/env python3
"""
验证 Agent Q&A API 集成是否成功
"""

import sys
import os

# Add parent directory to path to import chat_client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chat_client import get_available_apis, get_chat_response
import json


def test_api_listing():
    """测试API是否出现在列表中"""
    print("=" * 60)
    print("测试 1: 检查API配置")
    print("=" * 60)
    
    apis = get_available_apis()
    print(f"可用的API列表: {apis}")
    
    if "Agent Q&A" in apis:
        print("✅ Agent Q&A API 已成功添加到配置中")
        return True
    else:
        print("❌ Agent Q&A API 未在配置中找到")
        return False


def test_api_call():
    """测试API调用功能"""
    print("\n" + "=" * 60)
    print("测试 2: 测试API调用")
    print("=" * 60)
    
    test_message = "你好，这是一条测试消息"
    
    try:
        print(f"发送测试消息: {test_message}")
        response = get_chat_response(
            message=test_message,
            api_name="Agent Q&A",
            user_id="test_user_001",
            session_id="test_session_001"
        )
        
        print(f"\n收到响应:")
        print("-" * 60)
        
        # 尝试解析JSON响应
        try:
            response_data = json.loads(response)
            print(f"✅ 响应格式正确 (JSON)")
            print(f"\n结果字段:")
            print(f"  - result: {response_data.get('result', 'N/A')[:100]}...")
            print(f"  - thinking: {len(response_data.get('thinking', ''))} 字符")
            print(f"  - inform_base: {len(response_data.get('inform_base', ''))} 字符")
            print(f"  - raw: {len(response_data.get('raw', ''))} 字符")
            print(f"  - ttft: {response_data.get('ttft', 0):.2f} 秒")
            
            if response_data.get('result'):
                print("\n✅ API调用成功，收到响应内容")
                return True
            else:
                print("\n⚠️  API调用返回空内容")
                return False
                
        except json.JSONDecodeError:
            print(f"⚠️  响应不是JSON格式:")
            print(response[:500])
            
            # 检查是否是错误消息
            if "Error" in response or "❌" in response:
                print("\n⚠️  API调用返回错误（可能是网络问题或服务未就绪）")
                return False
            
            return False
            
    except Exception as e:
        print(f"\n❌ API调用失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n🔍 开始验证 Agent Q&A API 集成\n")
    
    results = []
    
    # 测试1: API列表
    results.append(("API配置检查", test_api_listing()))
    
    # 测试2: API调用
    results.append(("API调用测试", test_api_call()))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 所有测试通过！Agent Q&A API 已成功集成到系统中。")
        print("\n📝 下一步:")
        print("  1. 在UI中选择 'Agent Q&A' API")
        print("  2. 添加测试用例")
        print("  3. 开始测试")
    else:
        print("\n⚠️  部分测试失败。请检查:")
        print("  1. 配置文件是否正确")
        print("  2. 网络连接是否正常")
        print("  3. 服务是否可访问")
    
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
