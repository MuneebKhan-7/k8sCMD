"""
Test suite for LLM.py module
Tests the GWDG LLM service integration
"""

import sys
import os

# Add parent directory to path so we can import LLM
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from LLM import llm, LLM


def test_connection():
    """Test the connection to GWDG LLM service"""
    print("\n" + "="*60)
    print("TEST 1: Testing LLM Connection")
    print("="*60)
    
    try:
        result = llm.test_connection()
        print(f"✓ Connection test passed: {result}")
        return True
    except Exception as e:
        print(f"✗ Connection test failed: {e}")
        return False


def test_send_request():
    """Test sending a simple request to the LLM"""
    print("\n" + "="*60)
    print("TEST 2: Testing send_request()")
    print("="*60)
    
    try:
        query = "What is 2 + 2?"
        print(f"Query: {query}")
        response = llm.send_request(query)
        print(f"Response: {response}")
        
        if response and "Error" not in response:
            print("✓ send_request test passed")
            return True
        else:
            print("✗ send_request test failed")
            return False
    except Exception as e:
        print(f"✗ send_request test failed with exception: {e}")
        return False


def test_chat():
    """Test the chat method"""
    print("\n" + "="*60)
    print("TEST 3: Testing chat()")
    print("="*60)
    
    try:
        prompt = "Hello, how are you?"
        print(f"Prompt: {prompt}")
        response = llm.chat(prompt)
        print(f"Response: {response}")
        
        if response and "content" in response:
            print("✓ chat test passed")
            return True
        else:
            print("✗ chat test failed")
            return False
    except Exception as e:
        print(f"✗ chat test failed with exception: {e}")
        return False


def test_custom_model():
    """Test initializing LLM with a custom model"""
    print("\n" + "="*60)
    print("TEST 4: Testing Custom Model Initialization")
    print("="*60)
    
    try:
        custom_llm = LLM(model="meta-llama-3.1-8b-instruct")
        print(f"Model initialized: {custom_llm.model}")
        print("✓ Custom model initialization test passed")
        return True
    except Exception as e:
        print(f"✗ Custom model initialization test failed: {e}")
        return False


def test_system_prompt():
    """Test setting a custom system prompt"""
    print("\n" + "="*60)
    print("TEST 5: Testing set_system_prompt()")
    print("="*60)
    
    try:
        original_prompt = llm.system_prompt
        new_prompt = "You are an expert Python programmer."
        llm.set_system_prompt(new_prompt)
        
        print(f"Original prompt: {original_prompt}")
        print(f"New prompt: {llm.system_prompt}")
        
        if llm.system_prompt == new_prompt:
            # Restore original prompt
            llm.set_system_prompt(original_prompt)
            print("✓ set_system_prompt test passed")
            return True
        else:
            print("✗ set_system_prompt test failed")
            return False
    except Exception as e:
        print(f"✗ set_system_prompt test failed: {e}")
        return False


def run_all_tests():
    """Run all tests and report results"""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "GWDG LLM TEST SUITE".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    results = {
        "Connection Test": test_connection(),
        "Send Request Test": test_send_request(),
        "Chat Test": test_chat(),
        "Custom Model Test": test_custom_model(),
        "System Prompt Test": test_system_prompt(),
    }
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name}: {status}")
    
    print("-"*60)
    print(f"Total: {passed}/{total} tests passed")
    print("="*60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
