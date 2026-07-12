import os
import shutil
from PIL import Image, ImageDraw

# Directories
brain_dir = r"C:\Users\me\.gemini\antigravity\brain\134c96d3-56bf-4693-9a9e-e169f36cb931"
project_dir = r"\\wsl.localhost\Ubuntu\home\me\repos\helpful-agents\ontario-parks"
artefacts_dir = os.path.join(project_dir, "artefacts")

# Create artefacts directory if needed
os.makedirs(artefacts_dir, exist_ok=True)

# List of input files in chronological order
brain_files = sorted([f for f in os.listdir(brain_dir) if f.startswith("media__178389")])

# Output names in natural order
outputs = [
    "01_search.png",
    "02_grid.png",
    "03_review_details.png",
    "04_shopping_cart.png",
    "05_sign_in.png",
    "06_review_policies.png",
    "07_confirm_account.png",
    "08_occupant_details.png",
    "09_additional_info.png",
    "10_confirm_booking.png",
    "11_success_page.png",
    "12_preregister_page.png",
    "13_preregistered_success.png",
    "14_menu_all_bookings.png",
    "15_my_reservations.png",
    "16_reservation_details_cancel.png"
]

print(f"Redacting and copying {len(brain_files)} screenshots to {artefacts_dir}...")

for idx, f in enumerate(brain_files):
    src_path = os.path.join(brain_dir, f)
    dst_name = outputs[idx]
    dst_path = os.path.join(artefacts_dir, dst_name)
    
    # Open image
    img = Image.open(src_path)
    # Ensure it is RGB
    if img.mode != "RGB":
        img = img.convert("RGB")
        
    draw = ImageDraw.Draw(img)
    
    # Redact coordinates based on specific images
    if dst_name == "05_sign_in.png":
        # Redact email input field
        draw.rectangle([430, 640, 750, 720], fill=(255, 255, 255))
        # Redact password input field
        draw.rectangle([430, 740, 810, 810], fill=(255, 255, 255))
        
    elif dst_name == "07_confirm_account.png":
        # Redact personal account details box
        draw.rectangle([60, 480, 400, 860], fill=(255, 255, 255))
        # Draw placeholder text
        draw.text((100, 520), "[REDACTED PERSONAL INFO]", fill=(120, 120, 120))
        
    elif dst_name == "09_additional_info.png":
        # Redact Pass Number field
        draw.rectangle([410, 690, 600, 735], fill=(255, 255, 255))
        # Redact License Plate field
        draw.rectangle([140, 890, 260, 920], fill=(255, 255, 255))
        
    elif dst_name == "12_preregister_page.png" or dst_name == "13_preregistered_success.png":
        # Redact License Plate field
        draw.rectangle([390, 775, 560, 810], fill=(255, 255, 255))
        
    elif dst_name == "15_my_reservations.png":
        # Redact Occupant name
        draw.rectangle([510, 660, 630, 730], fill=(255, 255, 255))
        # Redact Vehicle plate
        draw.rectangle([640, 660, 720, 730], fill=(255, 255, 255))
        
    elif dst_name == "16_reservation_details_cancel.png":
        # Redact Occupant name
        draw.rectangle([440, 500, 560, 540], fill=(255, 255, 255))
        # Redact Vehicle plate
        draw.rectangle([570, 540, 640, 570], fill=(255, 255, 255))
        
    # Save image
    img.save(dst_path)
    print(f" - Processed: {dst_name}")

print("Redaction completed successfully!")
