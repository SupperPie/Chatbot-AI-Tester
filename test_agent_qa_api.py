#!/usr/bin/env python3
"""
测试 agent-question-and-answer API 连通性
用途：验证新接口是否可以调用成功
"""

import requests
import uuid
import time
import json
import sys


def test_agent_qa_stream(
    url: str,
    query: str = "你好，测试消息",
    user_id: str = None,
    thread_id: str = None,
    lob: str = "dc"
):
    """
    测试 agent-question-and-answer 流式接口
    
    参数：
        url: API地址
        query: 查询内容
        user_id: 用户ID
        thread_id: 会话ID
        lob: 业务线 (dc 或 ata)
    """
    # 生成测试ID
    if user_id is None:
        user_id = f"test_user_{str(uuid.uuid4())[:8]}"
    if thread_id is None:
        thread_id = f"test_thread_{str(uuid.uuid4())[:8]}"
    
    # 构建请求payload
    payload = {
        "query": query,
        "user_id": user_id,
        "thread_id": thread_id,
        "lob": lob
    }
    
    # 请求头
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    
    print("=" * 60)
    print("开始测试 Agent Q&A API")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"请求参数:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("-" * 60)
    
    try:
        # 发送请求
        start_time = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] 发送请求...")
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            stream=True,
            timeout=30
        )
        
        connect_time = time.time() - start_time
        print(f"[{time.strftime('%H:%M:%S')}] 连接成功! (耗时: {connect_time:.2f}秒)")
        print(f"HTTP状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print("-" * 60)
        
        # 检查状态码
        if response.status_code != 200:
            print(f"❌ 错误: HTTP {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
        
        # 处理流式响应
        print("开始接收流式响应:")
        print("-" * 60)
        
        chunk_count = 0
        first_chunk_time = None
        
        for line in response.iter_lines():
            if line:
                chunk_count += 1
                if first_chunk_time is None:
                    first_chunk_time = time.time() - start_time
                
                decoded_line = line.decode('utf-8')
                print(f"[Chunk {chunk_count}] {decoded_line[:200]}")
                
                # 解析 Server-Sent Events 格式
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:]
                    if data_str.strip() == "[DONE]":
                        print("\n✅ 接收完成标志: [DONE]")
                        break
                    
                    # 尝试解析JSON
                    try:
                        data_json = json.loads(data_str)
                        print(f"    解析结果: {json.dumps(data_json, ensure_ascii=False)[:150]}")
                    except json.JSONDecodeError:
                        pass
        
        total_time = time.time() - start_time
        
        print("-" * 60)
        print("测试统计:")
        print(f"  ✓ 总耗时: {total_time:.2f}秒")
        print(f"  ✓ 首包时间: {first_chunk_time:.2f}秒" if first_chunk_time else "  - 未收到数据")
        print(f"  ✓ 接收块数: {chunk_count}")
        print("=" * 60)
        print("✅ 测试成功! API可以正常调用")
        print("=" * 60)
        
        return True
        
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ 连接失败: 无法连接到 {url}")
        print(f"错误信息: {str(e)}")
        print("\n可能原因:")
        print("  1. 服务未启动或不可达")
        print("  2. 网络不通（检查VPN/网络配置）")
        print("  3. URL地址错误")
        print("  4. 防火墙/安全组限制")
        return False
        
    except requests.exceptions.Timeout:
        print(f"\n❌ 请求超时: 30秒内未收到响应")
        print("可能原因:")
        print("  1. 服务响应过慢")
        print("  2. 网络延迟过高")
        return False
        
    except Exception as e:
        print(f"\n❌ 发生错误: {type(e).__name__}")
        print(f"错误详情: {str(e)}")
        return False


def quick_connectivity_test(url: str):
    """快速连通性测试（不依赖流式响应）"""
    print("=" * 60)
    print("快速连通性测试")
    print("=" * 60)
    
    try:
        # 尝试简单的POST请求
        response = requests.post(
            url,
            json={
                "query": "test",
                "user_id": "test",
                "thread_id": "test",
                "lob": "dc"
            },
            headers={"Content-Type": "application/json"},
            timeout=5,
            stream=False
        )
        print(f"✅ 服务可达! HTTP状态码: {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到服务器")
        return False
    except Exception as e:
        print(f"⚠️  连接测试异常: {str(e)}")
        return False


if __name__ == "__main__":
    # 接口地址
    API_URL = "http://agent-question-and-answer.platform-ai.svc.dragon/stream"
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        test_query = sys.argv[1]
    else:
        test_query = "你好，这是一条测试消息"
    
    if len(sys.argv) > 2:
        test_lob = sys.argv[2]
    else:
        test_lob = "dc"
    
    # 首先进行快速连通性测试
    print(f"\n目标API: {API_URL}\n")
    if not quick_connectivity_test(API_URL):
        print("\n💡 提示：如果在Kubernetes集群内，请确保:")
        print("   - 服务名解析正确")
        print("   - Pod网络互通")
        print("   - 服务端口正确")
        sys.exit(1)
    
    print("\n")
    
    # 执行完整的流式测试
    success = test_agent_qa_stream(
        url=API_URL,
        query=test_query,
        lob=test_lob
    )
    
    sys.exit(0 if success else 1)
