import os
import uuid
import sys
import io

# Ensure UTF-8 output on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import requests
from flask import Flask, request, jsonify, send_file, after_this_request

# Add root folder to sys.path to allow importing backend.* modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.translation.indictrans import load_model
from backend.document.docx_processor import translate_docx

# Path to frontend: prefer built dist/ folder, fallback to frontend/ for local dev
DIST_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist'))
SRC_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
STATIC_FOLDER = DIST_FOLDER if os.path.isdir(DIST_FOLDER) else SRC_FOLDER

app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Limit uploads to 16MB

# Internal service binding: injected by Vercel when this service calls the backend
BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")

UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), 'uploads'))
OUTPUT_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), 'outputs'))

# Create folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# In-memory progress tracking for real-time translation status
job_progress = {}

# Pre-load translation model once during startup
if not BACKEND_URL:
    print(f"[DocTranslate] Serving static frontend from: {STATIC_FOLDER}")
    print("[DocTranslate] Starting backend and pre-loading translation model once...")
    load_model(force_cpu=False)
else:
    print(f"[DocTranslate] Gateway service initialized. Bound BACKEND_URL={BACKEND_URL}")

@app.route('/')
def index():
    """Serves the frontend homepage."""
    return app.send_static_file('index.html')

@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    if BACKEND_URL:
        try:
            resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
            return (resp.content, resp.status_code, resp.headers.items())
        except Exception as e:
            return jsonify({"status": "error", "error": f"Backend unreachable: {str(e)}"}), 502
    return jsonify({"status": "ok"})

@app.route('/progress/<job_id>', methods=['GET'])
@app.route('/api/progress/<job_id>', methods=['GET'])
def get_progress(job_id):
    """Returns current translation percentage and status message."""
    if BACKEND_URL:
        try:
            resp = requests.get(f"{BACKEND_URL}/progress/{job_id}", timeout=5)
            return (resp.content, resp.status_code, resp.headers.items())
        except Exception as e:
            return jsonify({"percent": 0, "message": f"Connecting to translation service... ({str(e)})"}), 200
    progress = job_progress.get(job_id, {"percent": 0, "message": "Initializing..."})
    return jsonify(progress)

@app.route('/test-translation', methods=['GET'])
@app.route('/api/test-translation', methods=['GET'])
def test_translation_endpoint():
    """
    Standalone endpoint that translates 'Welcome to our college.'
    to verify that IndicTrans2 is working directly.
    """
    if BACKEND_URL:
        try:
            resp = requests.get(f"{BACKEND_URL}/test-translation", timeout=60)
            return (resp.content, resp.status_code, resp.headers.items())
        except Exception as e:
            return jsonify({
                "status": "error",
                "error": f"Backend service unreachable: {str(e)}"
            }), 502

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
@app.route('/api/translate', methods=['POST'])
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

    if BACKEND_URL:
        try:
            files = {'file': (file.filename, file.stream, file.mimetype or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
            params = request.args.to_dict()
            resp = requests.post(f"{BACKEND_URL}/translate", files=files, params=params, timeout=300)
            
            excluded_headers = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
            headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded_headers]
            return (resp.content, resp.status_code, headers)
        except Exception as e:
            return jsonify({"error": f"Failed to forward translation request to backend: {str(e)}"}), 502

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
            
        # Setup progress callback
        job_id = request.args.get('job_id')
        def progress_callback(pct, msg):
            if job_id:
                job_progress[job_id] = {"percent": pct, "message": msg}

        progress_callback(2, "Document uploaded successfully...")

        # Parse batch size from query params if specified
        batch_size = request.args.get('batch_size', type=int)
        
        # Run document translation with automatic CPU fallback on CUDA issues
        try:
            translate_docx(
                input_path,
                output_path,
                batch_size=batch_size,
                force_cpu=False,
                progress_callback=progress_callback
            )
        except Exception as docx_err:
            is_cuda_err = "cuda" in str(docx_err).lower() or "out of memory" in str(docx_err).lower()
            if is_cuda_err:
                print(f"[DocTranslate] CUDA error encountered in translate route. Retrying document on CPU: {docx_err}")
                progress_callback(30, "CUDA memory limit reached. Processing safely on CPU...")
                translate_docx(
                    input_path,
                    output_path,
                    batch_size=2,
                    force_cpu=True,
                    progress_callback=progress_callback
                )
            else:
                raise docx_err
        
        progress_callback(100, "Translation completed successfully!")
        print("[DocTranslate] Translation successful")
        
        original_name_without_ext = os.path.splitext(file.filename)[0]
        download_name = f"{original_name_without_ext}_marathi.docx"
        
        # Read file into memory buffer to avoid Windows file lock errors
        with open(output_path, 'rb') as f:
            file_bytes = f.read()
            
        # Clean up temporary disk files immediately
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            print(f"Cleanup note: {e}")
            
        @after_this_request
        def cleanup_job(response):
            # Clean up job_progress record
            if job_id:
                job_progress.pop(job_id, None)
            return response
        
        return send_file(
            io.BytesIO(file_bytes),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
    except Exception as e:
        if job_id:
            job_progress[job_id] = {"percent": 0, "message": f"Error: {str(e)}"}
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

@app.errorhandler(404)
def not_found(e):
    """Fallback handler for SPA routing and 404 errors."""
    if request.path.startswith('/api/') or request.path in ('/health', '/translate', '/progress', '/test-translation'):
        return jsonify({"error": "Resource not found"}), 404
    if os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return app.send_static_file('index.html')
    return jsonify({"error": "Resource not found"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False)
