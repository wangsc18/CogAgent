#!/usr/bin/env python3
"""
测试第三方OpenAI API连接
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

print("=" * 80)
print("🔍 环境变量检查")
print("=" * 80)
print(f"OPENAI_BASE_URL = {os.getenv('OPENAI_BASE_URL')}")
print(f"OPENAI_API_KEY = {os.getenv('OPENAI_API_KEY')[:20]}..." if os.getenv('OPENAI_API_KEY') else "未设置")
print()

# 测试1: 使用原生OpenAI SDK
print("=" * 80)
print("📡 测试1: 使用原生 OpenAI SDK")
print("=" * 80)

try:
    import openai

    # 方案A: 使用环境变量
    print("\n[方案A] 使用环境变量中的 OPENAI_BASE_URL")
    client_a = openai.OpenAI(
        api_key=os.getenv('OPENAI_API_KEY'),
        base_url=os.getenv('OPENAI_BASE_URL')
    )
    print(f"  构造的base_url: {client_a.base_url}")

    response_a = client_a.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "你好"}],
        max_tokens=10
    )

    print(f"✅ 成功! 响应类型: {type(response_a)}")
    print(f"✅ 响应内容: {response_a.choices[0].message.content}")

except Exception as e:
    print(f"❌ 失败: {e}")
    print(f"   错误类型: {type(e)}")

    # 方案B: 手动添加 /v1
    print("\n[方案B] 手动添加 /v1 路径")
    try:
        base_url = os.getenv('OPENAI_BASE_URL', '')
        if not base_url.endswith('/v1'):
            base_url = base_url.rstrip('/') + '/v1'

        print(f"  修正后的base_url: {base_url}")

        client_b = openai.OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            base_url=base_url
        )

        response_b = client_b.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "你好"}],
            max_tokens=10
        )

        print(f"✅ 成功! 响应类型: {type(response_b)}")
        print(f"✅ 响应内容: {response_b.choices[0].message.content}")

    except Exception as e2:
        print(f"❌ 也失败: {e2}")

# 测试2: 使用 LangChain
print("\n" + "=" * 80)
print("📡 测试2: 使用 LangChain ChatOpenAI")
print("=" * 80)

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage

    print("\n[方案A] 使用环境变量")
    llm_a = ChatOpenAI(model='gpt-4o-mini', temperature=0, max_tokens=10)
    print(f"  LangChain构造的配置: base_url={llm_a.openai_api_base}")

    response_a = llm_a.invoke([HumanMessage(content="你好")])
    print(f"✅ 成功! 响应: {response_a.content}")

except Exception as e:
    print(f"❌ 失败: {e}")

    # 方案B: 显式指定 base_url
    print("\n[方案B] 显式指定 base_url")
    try:
        base_url = os.getenv('OPENAI_BASE_URL', '')
        if not base_url.endswith('/v1'):
            base_url = base_url.rstrip('/') + '/v1'

        print(f"  修正后的base_url: {base_url}")

        llm_b = ChatOpenAI(
            model='gpt-4o-mini',
            temperature=0,
            max_tokens=10,
            openai_api_key=os.getenv('OPENAI_API_KEY'),
            openai_api_base=base_url
        )

        response_b = llm_b.invoke([HumanMessage(content="你好")])
        print(f"✅ 成功! 响应: {response_b.content}")

    except Exception as e2:
        print(f"❌ 也失败: {e2}")

print("\n" + "=" * 80)
print("✅ 测试完成")
print("=" * 80)
