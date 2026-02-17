#!/usr/bin/env python3
import asyncio
from dotenv import load_dotenv
from copilot import CopilotClient
from src.multi_agent import MultiAgentTask

# Load environment variables
load_dotenv(override=True)

async def main():
    async with CopilotClient() as client:
        # Create the task component (Reusable)
        task_runner = MultiAgentTask(client)

        print("=== Test Case 1: Simple Request ===")
        user_prompt_1 = "Write a Python function to add two numbers."
        result_1 = await task_runner.run(user_prompt_1)
        
        print("\n--- Execution Logs ---")
        for log in result_1.messages:
            print(log)
            
        print("\n--- Final Result ---")
        print(result_1.code if result_1.success else "Failed to generate valid code.")


        print("\n\n=== Test Case 2: Specific Requirement ===")
        # 要求必須包含 Type Hints 和 Docstring，看 Reviewer 是否會抓
        user_prompt_2 = "Write a Python function to calculate Fibonacci numbers. It MUST utilize recursion and include Type Hints."
        result_2 = await task_runner.run(user_prompt_2)
        
        print("\n--- Execution Logs ---")
        for log in result_2.messages:
            print(log)
            
        print("\n--- Final Result ---")
        print(result_2.code if result_2.success else "Failed to generate valid code.")

if __name__ == "__main__":
    asyncio.run(main())
