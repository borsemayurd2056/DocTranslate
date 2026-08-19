import torch
import sys
import os
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from IndicTransToolkit.processor import IndicProcessor

# Global translation components
model = None
tokenizer = None
ip = None
device = None

def get_device(force_cpu=False):
    global device
    if force_cpu:
        return "cpu"
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    return device

def load_model(force_cpu=False):
    """Loads tokenizer and model once into memory."""
    global model, tokenizer, ip, device
    
    target_device = get_device(force_cpu=force_cpu)
    
    if model is not None:
        current_device = next(model.parameters()).device.type
        if current_device != target_device:
            print(f"[DocTranslate] Moving loaded model from {current_device} to {target_device}...")
            sys.stdout.flush()
            model = model.to(target_device)
            device = target_device
        return
    
    print(f"[DocTranslate] Loading IndicTrans2 on {target_device}...")
    sys.stdout.flush()
    
    device = target_device
    model_name = "ai4bharat/indictrans2-en-indic-dist-200M"
    
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True
    )
    
    model = AutoModelForSeq2SeqLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        dtype="auto"
    ).to(target_device)
    
    ip = IndicProcessor(inference=True)
    print(f"[DocTranslate] Model loaded successfully on {target_device}")
    sys.stdout.flush()

def translate_batch(texts, src_lang="eng_Latn", tgt_lang="mar_Deva", batch_size=None, force_cpu=False):
    """
    Translates a batch of texts from src_lang to tgt_lang.
    Uses batching internally to prevent GPU VRAM OOM errors.
    Supports automatic CPU fallback in case of CUDA OOM.
    """
    global model, device
    if not texts:
        return []
        
    load_model(force_cpu=force_cpu)
    
    # Identify actual device of model before generation
    dev = next(model.parameters()).device.type
    print(f"[DocTranslate] Document translation device: {dev}")
    sys.stdout.flush()
    
    if batch_size is None:
        batch_size = int(os.environ.get("TRANSLATION_BATCH_SIZE", 2))
    
    translations = []
    total_texts = len(texts)
    total_batches = (total_texts + batch_size - 1) // batch_size
    
    try:
        for batch_idx, i in enumerate(range(0, total_texts, batch_size)):
            batch_num = batch_idx + 1
            print(f"[DocTranslate] Device: {dev}")
            print(f"[DocTranslate] Translation batch: {batch_num}/{total_batches}")
            sys.stdout.flush()
            
            chunk = texts[i:i+batch_size]
            
            # Preprocess
            batch = ip.preprocess_batch(
                chunk,
                src_lang=src_lang,
                tgt_lang=tgt_lang
            )
            
            # Tokenize
            inputs = tokenizer(
                batch,
                truncation=True,
                padding="longest",
                return_tensors="pt",
                return_attention_mask=True
            ).to(dev)
            
            # Calculate dynamic max_length based on input sequence length to avoid unnecessarily large values
            max_input_len = inputs["input_ids"].shape[1]
            max_gen_length = min(256, max(64, int(max_input_len * 1.5) + 20))
            
            # Generate translation
            with torch.inference_mode():
                generated_tokens = model.generate(
                    **inputs,
                    use_cache=False,
                    min_length=0,
                    max_length=max_gen_length,
                    num_beams=5,
                    num_return_sequences=1
                )
                
            # Move tokens to CPU immediately and release GPU references
            generated_tokens_cpu = generated_tokens.detach().cpu().tolist()
            
            # Delete references
            del inputs, generated_tokens
            if dev == "cuda":
                torch.cuda.empty_cache()
                
            # Decode
            decoded_tokens = tokenizer.batch_decode(
                generated_tokens_cpu,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True
            )
            
            # Postprocess
            chunk_translations = ip.postprocess_batch(
                decoded_tokens,
                lang=tgt_lang
            )
            
            translations.extend(chunk_translations)
            
        return translations
        
    except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
        is_oom = "out of memory" in str(e).lower() or "cuda" in str(e).lower()
        if is_oom and dev == "cuda":
            print(f"[DocTranslate] CUDA Out of Memory detected. Safely falling back to CPU. Error: {safe_err_log(e)}")
            sys.stdout.flush()
            
            # Delete local references to GPU tensors to free up memory before retrying
            if 'inputs' in locals():
                del inputs
            if 'generated_tokens' in locals():
                del generated_tokens
            
            # Force cleanup of cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
            # Move model to CPU
            if model is not None:
                model = model.to("cpu")
            device = "cpu"
            
            # Force cleanup of cache again
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
            # Retry entire translation batch on CPU
            return translate_batch(texts, src_lang=src_lang, tgt_lang=tgt_lang, batch_size=batch_size, force_cpu=True)
        else:
            raise e

def safe_err_log(e):
    return str(e).encode('ascii', errors='backslashreplace').decode('ascii')

def translate_text(text, src_lang="eng_Latn", tgt_lang="mar_Deva", force_cpu=False):
    """Translates a single block of text."""
    if not text or not text.strip():
        return text
    res = translate_batch([text], src_lang=src_lang, tgt_lang=tgt_lang, batch_size=1, force_cpu=force_cpu)
    return res[0] if res else ""
