import os
import sys

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Set up path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from backend.translation.indictrans import translate_text
    
    print("[DocTranslate] Starting direct standalone model translation test...")
    english_text = "Welcome to our college."
    print(f"English : {english_text}")
    
    marathi_text = translate_text(english_text)
    print(f"Marathi : {marathi_text}")
    
    expected = "आमच्या महाविद्यालयात तुमचे स्वागत आहे."
    if marathi_text.strip() == expected:
        print("[DocTranslate] Standalone test PASSED! Model returns correct Devanagari translation.")
    else:
        print("[DocTranslate] Standalone test WARNING! Translation works, but output text differs from expected.")
        print(f"Expected: {expected}")
        print(f"Got     : {marathi_text}")

except Exception as e:
    import traceback
    print("[DocTranslate] Standalone test FAILED!")
    traceback.print_exc()
    sys.exit(1)
