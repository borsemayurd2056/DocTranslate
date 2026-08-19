import os
import uuid
import sys

# Ensure UTF-8 output on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from flask import Flask, request, jsonify, send_file, after_this_request

# Add root folder to sys.path to allow importing backend.* modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.translation.indictrans import load_model
from backend.document.docx_processor import translate_docx

app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Limit uploads to 16MB

UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), 'uploads'))
OUTPUT_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), 'outputs'))

# Create folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Pre-load translation model during Flask startup on CPU
print("[DocTranslate] Starting backend and pre-loading model...")
load_model(force_cpu=True)

@app.route('/')
def index():
    """Serves the frontend homepage."""
    return app.send_static_file('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"})

@app.route('/test-translation', methods=['GET'])
def test_translation_endpoint():
    """
    Standalone endpoint that translates 'Welcome to our college.'
    to verify that IndicTrans2 is working directly.
    """
    try:
        print("[DocTranslate] Standalone test requested for text: 'Welcome to our college.'")
        from backend.translation.indictrans import translate_text
        result = translate_text("Welcome to our college.")
        print(f"[DocTranslate] Direct translation result successfully generated (Length: {len(result)})")
        return jsonify({
            "status": "success",
            "original": "Welcome to our college.",
            "translated": result
        })
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        safe_err = str(e).encode('ascii', errors='backslashreplace').decode('ascii')
        print(f"[DocTranslate] Standalone test translation failed: {safe_err}\n{err_msg}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "traceback": err_msg
        }), 500

@app.route('/translate', methods=['POST'])
def translate():
    """
    Receives an English DOCX document, translates it to Marathi,
    and returns the translated DOCX file for download.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected for uploading"}), 400
        
    if not file.filename.lower().endswith('.docx'):
        return jsonify({"error": "Invalid file format. Only .docx files are accepted."}), 400
        
    print(f"[DocTranslate] Received document: {file.filename}")
    
    # Generate unique names for safe handling of concurrent requests
    file_id = str(uuid.uuid4())
    input_filename = f"{file_id}_in.docx"
    output_filename = f"{file_id}_out.docx"
    
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    
    try:
        # Save uploaded file
        file.save(input_path)
        
        # Verify file is not empty or corrupted (0 bytes)
        if os.path.getsize(input_path) == 0:
            return jsonify({"error": "The uploaded DOCX file is empty (0 bytes)."}), 400
            
        # Parse batch size from query params if specified
        batch_size = request.args.get('batch_size', type=int)
        
        # Run document translation
        translate_docx(input_path, output_path, batch_size=batch_size)
        
        # Set up cleanup hook to delete temp files after sending the response
        @after_this_request
        def cleanup_temp_files(response):
            try:
                if os.path.exists(input_path):
                    os.remove(input_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception as e:
                safe_err = str(e).encode('ascii', errors='backslashreplace').decode('ascii')
                print(f"Error during cleanup of temporary files: {safe_err}")
            return response
            
        print("[DocTranslate] Translation successful")
        
        original_name_without_ext = os.path.splitext(file.filename)[0]
        download_name = f"{original_name_without_ext}_marathi.docx"
        
        return send_file(
            output_path,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
    except Exception as e:
        # Cleanup input and output file if error occurs
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
            except:
                pass
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
                
        import traceback
        err_msg = traceback.format_exc()
        safe_err = str(e).encode('ascii', errors='backslashreplace').decode('ascii')
        print(f"[DocTranslate] Translation Error: {safe_err}\n{err_msg}")
        return jsonify({
            "error": f"Failed to translate document: {str(e)}",
            "details": err_msg
        }), 500

if __name__ == '__main__':
    # Host on localhost/all interfaces on port 5000
    app.run(host='0.0.0.0', port=5000, debug=False)
