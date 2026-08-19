import os
import sys
import urllib.request
import urllib.parse
import json

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Set up path to import backend and test modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

API_URL = "http://127.0.0.1:5000"

def test_standalone_endpoint():
    print("\n--- Testing /test-translation endpoint ---")
    url = f"{API_URL}/test-translation"
    try:
        response = urllib.request.urlopen(url)
        data = json.loads(response.read().decode('utf-8'))
        print("Response received:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        assert data.get("status") == "success"
        print("Success! /test-translation verified.")
    except Exception as e:
        print(f"Error testing /test-translation: {e}")
        sys.exit(1)

def test_translate_endpoint():
    print("\n--- Testing /translate endpoint ---")
    upload_url = f"{API_URL}/translate?batch_size=2" # Override batch size to 2 to test configuration passing
    sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.docx")
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_translated.docx")
    
    if not os.path.exists(sample_path):
        print(f"Error: Sample file {sample_path} not found.")
        sys.exit(1)
        
    # Build multipart/form-data boundary and body
    boundary = "---BoundaryDocTranslateTests---"
    boundary_bytes = boundary.encode('utf-8')
    
    with open(sample_path, 'rb') as f:
        file_content = f.read()
        
    filename = os.path.basename(sample_path)
    
    body = []
    body.append(f"--{boundary}".encode('utf-8'))
    body.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode('utf-8'))
    body.append(b'Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    body.append(b'')
    body.append(file_content)
    body.append(f"--{boundary}--".encode('utf-8'))
    body.append(b'')
    
    request_body = b'\r\n'.join(body)
    
    req = urllib.request.Request(upload_url, data=request_body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    
    try:
        print("Uploading docx file to /translate...")
        response = urllib.request.urlopen(req)
        translated_content = response.read()
        
        with open(output_path, 'wb') as out_f:
            out_f.write(translated_content)
            
        print(f"Translated docx file saved to {output_path} (Size: {len(translated_content)} bytes)")
        
        # Verify the structure using the docx processor's verification logic
        from tests.test_docx_translation import verify_translated_docx
        verify_translated_docx(output_path)
        print("Success! /translate verified.")
        
    except Exception as e:
        print(f"Error testing /translate: {e}")
        if hasattr(e, 'read'):
            print("Error details:", e.read().decode('utf-8', errors='ignore'))
        sys.exit(1)

if __name__ == "__main__":
    test_standalone_endpoint()
    test_translate_endpoint()
