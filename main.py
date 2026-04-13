import asyncio
import json
import re
import httpx  # 如果报错请在终端执行: pip install httpx
from playwright.async_api import async_playwright
from openai import OpenAI, APIConnectionError, APITimeoutError

# 1. 基础配置
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"), 
    base_url="https://OPENAI_API_KEY.com/v1",
    timeout=30.0  # 增加超时时间，防止中转站响应慢
)

SYSTEM_PROMPT = """
你是一个高级网页自动化 Agent。
目标：搜集《崩坏：星穹铁道》“丰饶”命途（药师）的背景设定。
规则：
1. 绝对不要重复点击标记为 [已访问] 的链接。
2. 始终以 JSON 格式回复：{"action": "click", "id": 节点ID, "thought": "原因"} 或 {"action": "final_answer", "content": "结果"}
"""

async def run_agent():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        tab = await context.new_page()
        
        visited_urls = set()
        print("🚀 Agent 启动，正在搜集“丰饶”命途资料（重试加固版）...")
        
        try:
            await tab.goto("https://www.miyoushe.com/sr/search?keyword=丰饶命途设定")
            await tab.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"❌ 初始页面加载失败: {e}")
            return

        for step in range(15): 
            print(f"\n--- 🤖 步骤 {step + 1} ---")
            
            # --- 感知层 ---
            elements = await tab.query_selector_all("a, button, h3")
            dom_data = []
            for i, el in enumerate(elements):
                try:
                    if await el.is_visible():
                        href = await el.get_attribute("href")
                        text = await el.inner_text()
                        if text and len(text.strip()) > 5:
                            is_visited = any(full in (href or "") for full in visited_urls) if href else False
                            status = "[已访问]" if is_visited else "[未访问]"
                            dom_data.append({"id": i, "text": f"{status} {text.strip()[:35]}"})
                except: continue
            
            # --- 决策层（带重试机制） ---
            decision = None
            for retry in range(3): # 最多尝试 3 次
                try:
                    response = client.chat.completions.create(
                        model="gemini-2.5-pro", 
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"当前元素：{json.dumps(dom_data[:35], ensure_ascii=False)}"}
                        ]
                    )
                    raw_content = response if isinstance(response, str) else response.choices[0].message.content
                    json_match = re.search(r'\{.*\}', raw_content, re.DOTALL)
                    if json_match:
                        decision = json.loads(json_match.group(0))
                        break # 成功获取，跳出重试循环
                except (APIConnectionError, APITimeoutError):
                    print(f"⚠️ 网络连接异常，正在进行第 {retry+1} 次重试...")
                    await asyncio.sleep(3) # 等待 3 秒再试
                except Exception as e:
                    print(f"⚠️ 决策解析异常: {e}")
                    break

            if not decision:
                print("❌ 连续重试失败，跳过本步...")
                continue

            print(f"💡 AI 思考: {decision.get('thought')}")

            # --- 执行层 ---
            action = decision.get("action")
            if action == "click":
                target_id = decision.get("id")
                if target_id is not None and target_id < len(elements):
                    target_el = elements[target_id]
                    href = await target_el.get_attribute("href")
                    if href: visited_urls.add(href)
                    
                    await target_el.evaluate("el => { el.style.border = '4px solid red'; el.scrollIntoView(); }")
                    await asyncio.sleep(1)
                    await target_el.click()
                    await tab.wait_for_load_state("networkidle", timeout=15000)
                
            elif action == "final_answer":
                print("\n✅ 任务完成！")
                print(decision.get("content"))
                break
            
            await asyncio.sleep(2) 

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_agent())
