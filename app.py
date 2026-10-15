import os
import sys
import tempfile
import time

# Ensure root folder is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Ensure UTF-8 output on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import gradio as gr
from backend.translation.indictrans import load_model, translate_text
from backend.document.docx_processor import translate_docx

# ZeroGPU integration for Hugging Face Spaces
try:
    import spaces
    has_spaces = True
    gpu_decorator = spaces.GPU(duration=180)
    print("[DocTranslate] Hugging Face Spaces ZeroGPU detected and enabled.")
except (ImportError, AttributeError):
    has_spaces = False
    def gpu_decorator(fn):
        return fn
    print("[DocTranslate] Running without spaces.GPU decorator (standard CUDA/CPU).")

# Pre-load translation model once on server startup
print("[DocTranslate] Pre-loading IndicTrans2 model...")
load_model(force_cpu=False)
print("[DocTranslate] Model ready.")

@gpu_decorator
def translate_document(file_obj, progress=gr.Progress()):
    """Translates an uploaded English .docx file into Marathi with formatting preserved."""
    if file_obj is None:
        raise gr.Error("Please upload an English .docx document.")
    
    input_path = file_obj.name if hasattr(file_obj, 'name') else str(file_obj)
    if not input_path.lower().endswith('.docx'):
        raise gr.Error("Only Microsoft Word documents (.docx) are supported.")
    
    filename = os.path.basename(input_path)
    base_name, ext = os.path.splitext(filename)
    # Clean temporary names if prefixed with random hashes
    output_filename = f"{base_name}_translated{ext}"
    output_path = os.path.join(tempfile.gettempdir(), output_filename)
    
    start_time = time.time()
    
    def on_progress(percent, message):
        progress(percent / 100.0, desc=message)
        
    try:
        progress(0.05, desc="Analyzing Word document structure & styles...")
        translate_docx(
            input_path=input_path,
            output_path=output_path,
            progress_callback=on_progress
        )
        elapsed = round(time.time() - start_time, 1)
        status_msg = f"Document translated successfully in {elapsed} seconds!"
        return output_path, status_msg
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise gr.Error(f"Translation failed: {str(e)}")

@gpu_decorator
def quick_text_translate(text):
    """Quick single sentence / paragraph translation test."""
    if not text or not text.strip():
        return ""
    start_time = time.time()
    try:
        translated = translate_text(text.strip())
        elapsed = round(time.time() - start_time, 2)
        return f"{translated}\n\n(Translated in {elapsed}s)"
    except Exception as e:
        return f"Error: {str(e)}"

# Define custom styling and Gradio interface
custom_css = """
.container { max-width: 960px; margin: auto; }
.header-box { text-align: center; margin-bottom: 1.5rem; }
.header-box h1 { font-size: 2.2rem; font-weight: 700; color: #1e3a8a; }
.header-box p { font-size: 1.05rem; color: #4b5563; }
.badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; background-color: #dbeafe; color: #1e40af; font-size: 0.85rem; font-weight: 600; margin-top: 0.5rem; }
"""

blocks_kwargs = {"title": "DocTranslate - English to Marathi"}
launch_kwargs = {"server_name": "0.0.0.0", "server_port": int(os.environ.get("PORT", 7860))}

try:
    if int(gr.__version__.split('.')[0]) >= 6:
        launch_kwargs["theme"] = gr.themes.Soft(primary_hue="blue", neutral_hue="slate")
        launch_kwargs["css"] = custom_css
    else:
        blocks_kwargs["theme"] = gr.themes.Soft(primary_hue="blue", neutral_hue="slate")
        blocks_kwargs["css"] = custom_css
except Exception:
    blocks_kwargs["title"] = "DocTranslate - English to Marathi"

with gr.Blocks(**blocks_kwargs) as demo:
    with gr.Column(elem_classes=["container"]):
        with gr.Column(elem_classes=["header-box"]):
            gr.Markdown(
                """
                # 🌐 DocTranslate
                ### English to Marathi Word Document Translator
                <span class="badge">AI4Bharat IndicTrans2 • ZeroGPU Accelerated • Layout & Style Preserving</span>
                
                Translate English `.docx` documents into Marathi (`मराठी`) while preserving bold, italics, underlines, font colors, table layouts, and paragraph alignments.
                """
            )
        
        with gr.Tabs():
            with gr.TabItem("📄 Document Translation (.docx)"):
                with gr.Row():
                    with gr.Column(scale=1):
                        file_input = gr.File(
                            label="Upload English Word Document",
                            file_types=[".docx"],
                            type="filepath"
                        )
                        translate_btn = gr.Button("🌐 Translate Document to Marathi", variant="primary", size="lg")
                        
                        sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "sample.docx")
                        if os.path.exists(sample_path):
                            gr.Examples(
                                examples=[[sample_path]],
                                inputs=file_input,
                                label="Sample Document"
                            )
                    
                    with gr.Column(scale=1):
                        file_output = gr.File(
                            label="Download Translated Marathi Document",
                            type="filepath"
                        )
                        status_output = gr.Markdown(value="*Upload a document and click 'Translate Document' to begin.*")
                
                translate_btn.click(
                    fn=translate_document,
                    inputs=[file_input],
                    outputs=[file_output, status_output]
                )
            
            with gr.TabItem("⚡ Quick Text Translation"):
                gr.Markdown("Test the IndicTrans2 model directly with any English sentence or paragraph.")
                with gr.Row():
                    with gr.Column():
                        text_input = gr.Textbox(
                            label="English Text",
                            placeholder="Enter English text here... (e.g., Welcome to our college.)",
                            lines=4
                        )
                        quick_btn = gr.Button("Translate Text", variant="primary")
                    with gr.Column():
                        text_output = gr.Textbox(
                            label="Marathi Translation (मराठी)",
                            lines=4,
                            interactive=False
                        )
                
                quick_btn.click(
                    fn=quick_text_translate,
                    inputs=[text_input],
                    outputs=[text_output]
                )
                
                gr.Examples(
                    examples=[
                        ["Welcome to our college."],
                        ["The annual sports event will be organized next Monday."],
                        ["Please submit your project report before the deadline."]
                    ],
                    inputs=text_input
                )

        with gr.Accordion("ℹ️ Features & Architecture", open=False):
            gr.Markdown(
                """
                - **Style & Markup Tagging**: Formatted runs within paragraphs (bold, italic, colors, fonts) are tagged with markup before translation and mapped back to the translated Marathi text.
                - **Sentence & Paragraph Context**: Translates whole sentences to preserve Marathi Subject-Object-Verb (SOV) grammatical structure.
                - **ZeroGPU Acceleration**: Runs on dynamically allocated Nvidia A100 GPU compute on Hugging Face Spaces for near-instant inference.
                - **Document Elements Supported**: Paragraphs, styled headings, multi-run styles, tables, and cell content.
                """
            )

if __name__ == "__main__":
    demo.queue().launch(**launch_kwargs)
