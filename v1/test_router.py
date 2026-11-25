import asyncio
from backend.llm.router import LLMRouter
router = LLMRouter(provider_timeout=15)
messages = [{"role": "user", "content": "Say OK"}]
for tier in ['strategic', 'coding', 'fast_eval']:
    print(f"\n--- Testing Tier: {tier} ---")
    try:
        reply = router.chat(messages, model_tier=tier)
        print(f"SUCCESS: {router.last_provider} / {router.last_model} -> {reply.thought.strip()}")
    except Exception as e:
        print(f"FAILED: {e}")
print("\nOperational Events Logged:")
for event in router._provider_events:
    print(event)
