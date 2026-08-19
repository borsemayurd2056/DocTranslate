import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import torch

# Set up path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding='utf-8')

import backend.translation.indictrans as indictrans

class TestCpuFallback(unittest.TestCase):
    def test_cpu_fallback_on_oom(self):
        print("\n--- Running CPU Fallback Test ---")
        
        # Ensure model is loaded and on CUDA if available
        indictrans.load_model()
        
        # Check if CUDA is available on this machine
        if not torch.cuda.is_available():
            print("CUDA not available. Simulating CUDA availability.")
            # Mock torch.cuda.is_available and get_device to return True and "cuda"
            is_available_mock = MagicMock(return_value=True)
            get_device_mock = MagicMock(return_value="cuda")
        else:
            is_available_mock = torch.cuda.is_available
            get_device_mock = indictrans.get_device

        # Reset global device to "cuda" for testing the fallback
        indictrans.device = "cuda"
        
        original_generate = indictrans.model.generate
        original_device_to = indictrans.model.to
        
        call_count = 0
        
        def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Raise CUDA OOM on the first call (which should be on CUDA)
            if call_count == 1:
                print("[Mock] Raising artificial CUDA OutOfMemoryError...")
                raise torch.cuda.OutOfMemoryError("CUDA out of memory (simulated)")
            # Succeed on subsequent calls
            return original_generate(*args, **kwargs)
            
        def mock_to(device, *args, **kwargs):
            print(f"[Mock] Moving model to: {device}")
            # Actually call the original to move the model
            return original_device_to(device, *args, **kwargs)

        with patch('torch.cuda.is_available', is_available_mock), \
             patch.object(indictrans.model, 'generate', side_effect=mock_generate), \
             patch.object(indictrans.model, 'to', side_effect=mock_to) as mock_model_to:
             
            english_text = "Welcome to our college."
            print(f"Translating: '{english_text}'")
            
            # Translate text
            marathi_text = indictrans.translate_text(english_text)
            
            print(f"Translation Output: '{marathi_text}'")
            
            # Assertions
            self.assertEqual(indictrans.device, "cpu")
            self.assertEqual(call_count, 2) # First call OOMed, second call succeeded on CPU
            mock_model_to.assert_any_call("cpu")
            
            print("Success! CPU fallback logic successfully verified.")
            
if __name__ == "__main__":
    unittest.main()
