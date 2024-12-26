from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import base64
from io import BytesIO

# Initialize BLIP model and processor
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

def filecaption(file):
    with open(file, "rb") as image_file:
        # Convert the image to base64
        base64_encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
        return get_image_caption_from_base64(base64_encoded_image)

def get_image_caption_from_base64(base64_str):
    img_bytes = base64.b64decode(base64_str)
    raw_image = Image.open(BytesIO(img_bytes)).convert('RGB')

    inputs = processor(raw_image, return_tensors="pt")
    outputs = model.generate(**inputs, max_new_tokens=100)
    caption = processor.decode(outputs[0], skip_special_tokens=True)

    return caption

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}
