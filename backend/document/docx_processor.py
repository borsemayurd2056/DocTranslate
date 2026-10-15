import os
import re
from docx import Document
from backend.translation.indictrans import translate_batch

def parse_tagged_text(tagged_text):
    """
    Parses a translated text containing HTML-like formatting tags (<b>, <i>, <u>)
    and returns a list of dictionaries with text segments and their style states.
    """
    # Split the text by tags, capturing the tags themselves
    parts = re.split(r'(</?[biu]>)', tagged_text)
    runs_data = []
    active_styles = {'b': False, 'i': False, 'u': False}
    
    for part in parts:
        if not part:
            continue
        
        if part == '<b>':
            active_styles['b'] = True
        elif part == '</b>':
            active_styles['b'] = False
        elif part == '<i>':
            active_styles['i'] = True
        elif part == '</i>':
            active_styles['i'] = False
        elif part == '<u>':
            active_styles['u'] = True
        elif part == '</u>':
            active_styles['u'] = False
        else:
            # This is standard text
            runs_data.append({
                'text': part,
                'bold': active_styles['b'],
                'italic': active_styles['i'],
                'underline': active_styles['u']
            })
            
    return runs_data

def paragraph_to_tagged_text(p):
    """
    Wraps styled runs in a paragraph with HTML-like tags for translation.
    """
    tagged_parts = []
    for run in p.runs:
        text = run.text
        if not text:
            continue
        
        bold = run.bold is True
        italic = run.italic is True
        underline = run.underline is True
        
        wrapped_text = text
        if bold:
            wrapped_text = f"<b>{wrapped_text}</b>"
        if italic:
            wrapped_text = f"<i>{wrapped_text}</i>"
        if underline:
            wrapped_text = f"<u>{wrapped_text}</u>"
            
        tagged_parts.append(wrapped_text)
        
    return "".join(tagged_parts)

def has_formatting_variation(p):
    """
    Checks if a paragraph has multiple runs with different formatting.
    """
    if len(p.runs) <= 1:
        return False
        
    # Get the style of the first run as reference
    first_r = p.runs[0]
    first_fmt = (first_r.bold is True, first_r.italic is True, first_r.underline is True)
    
    for r in p.runs[1:]:
        fmt = (r.bold is True, r.italic is True, r.underline is True)
        if fmt != first_fmt:
            return True
            
    return False

def translate_docx(input_path, output_path, batch_size=None, force_cpu=False, progress_callback=None):
    """
    Reads a DOCX file from input_path, translates all English text inside
    paragraphs and tables to Marathi, and saves the translated DOCX to output_path.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found at: {input_path}")
        
    if progress_callback:
        progress_callback(5, "Analyzing document structure and tables...")
        
    doc = Document(input_path)
    
    translatable_items = []
    
    # 1. Collect all non-empty paragraphs from the main document body
    for p in doc.paragraphs:
        if p.text.strip():
            translatable_items.append({
                'type': 'paragraph',
                'object': p
            })
            
    # 2. Collect all non-empty paragraphs from tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if p.text.strip():
                        translatable_items.append({
                            'type': 'paragraph',
                            'object': p
                        })
                        
    if not translatable_items:
        print("[DocTranslate] Extracted 0 paragraphs")
        doc.save(output_path)
        if progress_callback:
            progress_callback(100, "Empty document processed.")
        return
        
    print(f"[DocTranslate] Extracted {len(translatable_items)} paragraphs")
    if progress_callback:
        progress_callback(10, f"Extracted {len(translatable_items)} paragraphs...")
        
    # 3. Prepare texts for batch translation
    texts_to_translate = []
    for item in translatable_items:
        p = item['object']
        if has_formatting_variation(p):
            item['has_variation'] = True
            item['tagged_text'] = paragraph_to_tagged_text(p)
            texts_to_translate.append(item['tagged_text'])
        else:
            item['has_variation'] = False
            item['tagged_text'] = p.text
            texts_to_translate.append(p.text)
            
    # 4. Filter and deduplicate unique segments needing translation
    unique_to_translate = []
    seen = set()
    for t in texts_to_translate:
        stripped = t.strip()
        # Skip pure numbers, punctuation or symbols (e.g. '123', '505', '---', '1.')
        if not re.search(r'[a-zA-Z]', stripped):
            continue
        if stripped not in seen:
            seen.add(stripped)
            unique_to_translate.append(stripped)

    if progress_callback:
        progress_callback(15, f"Optimized {len(texts_to_translate)} items into {len(unique_to_translate)} unique segments...")

    # Perform batch translation on unique segments
    if unique_to_translate:
        print(f"[DocTranslate] Translating {len(unique_to_translate)} unique segments (out of {len(texts_to_translate)} total)")
        unique_translated = translate_batch(
            unique_to_translate,
            batch_size=batch_size,
            force_cpu=force_cpu,
            progress_callback=progress_callback
        )
        trans_map = dict(zip(unique_to_translate, unique_translated))
    else:
        trans_map = {}

    # Map translations back to all original items, preserving leading/trailing whitespace
    translated_texts = []
    for t in texts_to_translate:
        stripped = t.strip()
        if stripped in trans_map:
            l_ws = t[:len(t) - len(t.lstrip())]
            r_ws = t[len(t.rstrip()):]
            translated_texts.append(l_ws + trans_map[stripped] + r_ws)
        else:
            translated_texts.append(t)
            
    print("[DocTranslate] Translation completed")
    if progress_callback:
        progress_callback(92, "Preserving original formatting, fonts, and table structures...")
    
    # 5. Re-apply translated text to the document elements
    print("[DocTranslate] Creating translated DOCX")
    for item, translated_text in zip(translatable_items, translated_texts):
        p = item['object']
        
        # Save original font name and size from the first run (if any)
        orig_font_name = None
        orig_font_size = None
        orig_font_color = None
        orig_bold = False
        orig_italic = False
        orig_underline = False
        
        if p.runs:
            first_run = p.runs[0]
            orig_font_name = first_run.font.name
            orig_font_size = first_run.font.size
            if first_run.font.color and first_run.font.color.rgb:
                orig_font_color = first_run.font.color.rgb
            orig_bold = first_run.bold is True
            orig_italic = first_run.italic is True
            orig_underline = first_run.underline is True
            
        # Rebuild paragraph runs based on format variation
        if item['has_variation']:
            runs_data = parse_tagged_text(translated_text)
            p.text = "" # Clear original runs
            
            for r_data in runs_data:
                # Add a run with the text fragment
                new_run = p.add_run(r_data['text'])
                # Set formatting if it was active
                if r_data['bold']:
                    new_run.bold = True
                if r_data['italic']:
                    new_run.italic = True
                if r_data['underline']:
                    new_run.underline = True
                
                # Apply font properties from the original style
                if orig_font_name:
                    new_run.font.name = orig_font_name
                if orig_font_size:
                    new_run.font.size = orig_font_size
                if orig_font_color:
                    new_run.font.color.rgb = orig_font_color
        else:
            # Paragraph had uniform style, set translated text directly and apply formatting
            p.text = ""
            new_run = p.add_run(translated_text)
            if orig_bold:
                new_run.bold = True
            if orig_italic:
                new_run.italic = True
            if orig_underline:
                new_run.underline = True
                
            # Apply font properties
            if orig_font_name:
                new_run.font.name = orig_font_name
            if orig_font_size:
                new_run.font.size = orig_font_size
            if orig_font_color:
                new_run.font.color.rgb = orig_font_color
                
    if progress_callback:
        progress_callback(98, "Saving translated DOCX document...")
    doc.save(output_path)
    if progress_callback:
        progress_callback(100, "Translation completed successfully!")
