import asyncio
from backend.orchestrator.pipeline import MultiAgentPipeline
import json

def test_e2e():
    print("Testing Pipeline End-to-End...")
    pipeline = MultiAgentPipeline(config={"max_retries_per_subtask": 1, "budget": 100})
    spec = "Write a python script that prints 'End to End successful'"
    try:
        reply = pipeline.run("test_e2e", spec, "")
        print(f"SUCCESS: {reply}")
    except Exception as e:
        import traceback
        traceback.print_exc()

test_e2e()
