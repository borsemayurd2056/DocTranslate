import torch
import sys
import os
import transformers
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# Compatibility patch for IndicTransToolkit with modern transformers versions
try:
    import transformers.tokenization_utils_base
    import transformers.tokenization_utils
    if not hasattr(transformers.tokenization_utils, "PreTrainedTokenizerBase"):
        transformers.tokenization_utils.PreTrainedTokenizerBase = transformers.tokenization_utils_base.PreTrainedTokenizerBase
except Exception:
    pass

from IndicTransToolkit.processor import IndicProcessor

# Global translation components
model = None
tokenizer = None
ip = None
device = None

def get_device(force_cpu=False):
    global device
    if force_cpu or os.environ.get("FORCE_CPU", "").lower() in ("1", "true", "yes"):
        return "cpu"
    # Dynamically check cuda availability so ZeroGPU activation is immediately detected
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return device


def load_model(force_cpu=False):
    """Loads tokenizer and model once into memory."""
    global model, tokenizer, ip, device
    
    target_device = get_device(force_cpu=force_cpu)
    target_dtype = torch.float16 if target_device == "cuda" else torch.float32
    
    if model is not None:
        current_device = next(model.parameters()).device.type
        if current_device != target_device:
            print(f"[DocTranslate] Moving loaded model from {current_device} to {target_device}...")
            sys.stdout.flush()
            model = model.to(target_device, dtype=target_dtype)
            device = target_device
        return
    
    print(f"[DocTranslate] Loading IndicTrans2 on {target_device} ({target_dtype})...")
    sys.stdout.flush()
    
    device = target_device
    model_name = "ai4bharat/indictrans2-en-indic-dist-200M"
    
    # Configure model cache directory via HF_HOME
    cache_dir = os.environ.get("HF_HOME")
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    
    hf_token = os.environ.get("HF_TOKEN") or None

    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        token=hf_token,
        cache_dir=cache_dir
    )
    
    model = AutoModelForSeq2SeqLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        dtype=target_dtype,
        token=hf_token,
        cache_dir=cache_dir
    ).to(target_device)
    
    ip = IndicProcessor(inference=True)
    print(f"[DocTranslate] Model loaded successfully on {target_device}")
    sys.stdout.flush()

def translate_batch(texts, src_lang="eng_Latn", tgt_lang="mar_Deva", batch_size=None, num_beams=None, force_cpu=False, progress_callback=None):
    """
    Translates a batch of texts from src_lang to tgt_lang.
    Uses batching internally to prevent GPU VRAM OOM errors.
    Supports automatic CPU fallback in case of CUDA OOM.
    Includes AMP FP16 acceleration and progress callback reporting.
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
        env_bs = os.environ.get("TRANSLATION_BATCH_SIZE")
        if env_bs:
            batch_size = int(env_bs)
        else:
            batch_size = 2
            
    if num_beams is None:
        env_beams = os.environ.get("TRANSLATION_NUM_BEAMS")
        if env_beams:
            num_beams = int(env_beams)
        else:
            # 2 beams provides high accuracy while maintaining speed
            num_beams = 2
    
    translations = []
    total_texts = len(texts)
    total_batches = (total_texts + batch_size - 1) // batch_size
    
    try:
        for batch_idx, i in enumerate(range(0, total_texts, batch_size)):
            batch_num = batch_idx + 1
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
            
            # Calculate dynamic max_length based on input sequence length
            max_input_len = inputs["input_ids"].shape[1]
            max_gen_length = min(256, max(32, int(max_input_len * 1.4) + 16))
            
            # For very long paragraphs (>150 tokens), use greedy decoding (num_beams=1) to guarantee zero OOM
            batch_num_beams = 1 if max_input_len > 150 else num_beams
            
            print(f"[DocTranslate] Translation batch: {batch_num}/{total_batches} (Tokens: {max_input_len}, Beams: {batch_num_beams}, Device: {dev})")
            sys.stdout.flush()
            
            # Generate translation with inference mode
            with torch.inference_mode():
                if dev == "cuda":
                    with torch.amp.autocast(device_type="cuda", dtype=torch.float16):
                        generated_tokens = model.generate(
                            **inputs,
                            use_cache=False,
                            min_length=0,
                            max_length=max_gen_length,
                            num_beams=batch_num_beams,
                            num_return_sequences=1
                        )
                else:
                    generated_tokens = model.generate(
                        **inputs,
                        use_cache=False,
                        min_length=0,
                        max_length=max_gen_length,
                        num_beams=batch_num_beams,
                        num_return_sequences=1
                    )
                
            # Move tokens to CPU immediately and release GPU references
            generated_tokens_cpu = generated_tokens.detach().cpu().tolist()
            
            # Clean up references to free GPU memory immediately
            del inputs
            del generated_tokens
                
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
            
            # Update progress callback if provided
            if progress_callback:
                pct = 15 + int((batch_num / total_batches) * 75)
                progress_callback(pct, f"Translating batch {batch_num} of {total_batches} ({pct}%)...")
            
        return translations
        
    except Exception as e:
        is_oom = "out of memory" in str(e).lower() or "cuda" in str(e).lower() or isinstance(e, torch.cuda.OutOfMemoryError)
        if is_oom and dev == "cuda":
            print(f"[DocTranslate] CUDA error/OOM detected. Safely falling back to CPU. Error: {safe_err_log(e)}")
            sys.stdout.flush()
            
            # Safe cleanup of GPU tensors
            try:
                if 'inputs' in locals():
                    del inputs
                if 'generated_tokens' in locals():
                    del generated_tokens
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
                
            # Safely transition model to CPU
            try:
                if model is not None:
                    model = model.to("cpu")
                device = "cpu"
            except Exception as move_err:
                print(f"[DocTranslate] Note: Could not migrate GPU model to CPU ({move_err}). Recreating model on CPU...")
                sys.stdout.flush()
                model = None
                device = "cpu"
                load_model(force_cpu=True)
                
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
                
            # Retry entire translation on CPU
            return translate_batch(
                texts,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                batch_size=2,
                num_beams=num_beams,
                force_cpu=True,
                progress_callback=progress_callback
            )
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
