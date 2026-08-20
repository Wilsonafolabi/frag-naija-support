import asyncio, sys, traceback
sys.path.insert(0, '.')
from app.ai.groq import GroqProvider
from app.services.intent_classifier import IntentClassifier
from app.config import get_settings

async def main():
    settings = get_settings()
    llm = GroqProvider(settings)
    classifier = IntentClassifier(llm)
    try:
        print("Testing classifier directly...")
        res = await classifier.classify('What is Frag Naija?')
        print(f'SUCCESS: {res}')
    except Exception as e:
        print("CRASHED! Here is the exact line number:")
        traceback.print_exc()

asyncio.run(main())
