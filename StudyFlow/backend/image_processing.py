from PIL import ImageOps, ImageEnhance
import os
import time
from StudyFlow.config import DEBUG_DIR
from StudyFlow.logging_utils import debug_log

def preprocess_image_custom(image, contrast_factor, threshold_val):
    """Preprocess an image with given contrast factor and threshold value."""
    gray = ImageOps.grayscale(image)
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(contrast_factor)
    processed = enhanced.point(lambda x: 0 if x < threshold_val else 255, '1')
    return processed

def preprocess_image(image):
    debug_log("🔧 Starting image preprocessing.")

    try:
        gray = ImageOps.grayscale(image)
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(3.0)
        processed = enhanced.point(lambda x: 0 if x < 130 else 255, '1')

        # Default to safe directory
        safe_debug_dir = DEBUG_DIR or "/app/debug"
        if not os.path.exists(safe_debug_dir):
            os.makedirs(safe_debug_dir, exist_ok=True)

        debug_path = os.path.join(safe_debug_dir, f"processed_{int(time.time())}.png")
        processed.save(debug_path)
        debug_log(f"✅ Processed image saved to {debug_path}")

        return processed

    except Exception as e:
        debug_log(f"❌ Error during image preprocessing: {e}")
        raise  # re-raise so the Flask route can handle it
