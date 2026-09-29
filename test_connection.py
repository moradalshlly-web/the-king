"""
test_connection.py
==================

Quick test: can MOROAI reach Groq and get a response?
This file is temporary and will be deleted after the test.
"""

from providers.groq import GroqProvider


def main():
    print("Testing Groq connection...\n")

    provider = GroqProvider()

    if not provider.is_available():
        print("❌ Provider is not available. Check GROQ_API_KEY.")
        return

    print(f"✅ Provider available: {provider.name}")
    print(f"✅ Default model: {provider.config.models[0]}")
    print("📤 Sending test prompt...\n")

    response = provider.chat(
        prompt="Say 'MOROAI online' in Arabic, nothing else.",
        system="You are a helpful assistant. Reply briefly.",
        temperature=0.3,
    )

    print("─" * 50)
    if response.success:
        print(f"✅ SUCCESS")
        print(f"   Text      : {response.text}")
        print(f"   Model     : {response.model}")
        print(f"   Provider  : {response.provider}")
        print(f"   Tokens    : {response.tokens_used}")
        print(f"   Latency   : {response.latency_ms} ms")
    else:
        print(f"❌ FAILED")
        print(f"   Error     : {response.error}")
        print(f"   Code      : {response.error_code}")
    print("─" * 50)


if __name__ == "__main__":
    main()
