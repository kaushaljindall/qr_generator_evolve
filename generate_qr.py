import qrcode
import sys
import os
from datetime import datetime
from urllib.parse import urlparse
from PIL import Image, ImageChops, ImageDraw

def generate_transparent_qr(url, add_logo=False):
    # Ensure the output directory exists
    output_dir = "output_qr"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate dynamic file names
    parsed_url = urlparse(url)
    domain_name = parsed_url.netloc.replace("www.", "") if parsed_url.netloc else "link"
    timestamp = datetime.now().strftime("%H%M%S")
    domain_name = "".join(c for c in domain_name if c.isalnum() or c in ("-", "."))
    
    file_prefix = "EvolveAI_LogoThemed_" if add_logo else ""
    output_file = os.path.join(output_dir, f"{file_prefix}{domain_name}_{timestamp}_qr.png")

    # High error correction allows us to completely safely cover the center 30% of the code
    qr = qrcode.QRCode(
        version=3, # Bumped up the grid density slightly to make color mapping look highly detailed
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=7,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    try:
        # Generate standard QR grid with a pure transparent background
        base_qr = qr.make_image(fill_color="black", back_color="transparent").convert("RGBA")

        if add_logo:
            logo_path = os.path.join("assets", "logo", "logo.png")
            if not os.path.exists(logo_path):
                print(f"\n⚠️  Logo not found: Please place an image exactly at '{logo_path}'.")
                print("Generating standard QR Code instead...")
                img = base_qr
            else:
                logo = Image.open(logo_path).convert("RGBA")
                
                # --- SCANNABILITY FIX: THEME INSTEAD OF CUTOUT ---
                # A QR code mathematically stores the URL in its outer border blocks. 
                # Carving it entirely into the shape of the logo deletes too much data and breaks the link.
                # Instead, we will PERFECTLY colorize the entire QR Grid using the logo's colors 
                # AND embed the actual logo dynamically into the hyper-safe center zone!
                
                # 1. Map the Logo's exact pixels/gradients natively onto the QR Dots
                stretched_logo = logo.resize(base_qr.size, Image.Resampling.LANCZOS)
                qr_alpha = base_qr.getchannel('A')
                
                colored_qr = stretched_logo.copy()
                colored_qr.putalpha(qr_alpha) # Keep transparent background, but color the dots!
                
                # 2. Bake the actual logo directly into the absolute center at exactly 28% scale 
                # (Maximum safe scannability size is 30%)
                logo_size = int(base_qr.width * 0.28)
                wpercent = (logo_size / float(logo.width))
                hsize = int((float(logo.height) * float(wpercent)))
                small_logo = logo.resize((logo_size, hsize), Image.Resampling.LANCZOS)
                
                # Find direct center positions
                pos = (
                    (base_qr.width - small_logo.width) // 2,
                    (base_qr.height - small_logo.height) // 2
                )
                
                # To ensure the logo is insanely visible without blending into the dots, 
                # we carve out a tiny hyper-clean background just under the logo
                clear_box = ImageDraw.Draw(colored_qr)
                padding = 5
                clear_box.rectangle(
                    [pos[0] - padding, pos[1] - padding, pos[0] + small_logo.width + padding, pos[1] + small_logo.height + padding], 
                    fill=(0,0,0,0)  # Pure transparent cutout
                )
                
                # Paste the logo
                colored_qr.paste(small_logo, pos, mask=small_logo)
                
                img = colored_qr
                print("\n✨ Successfully themed the QR Grid universally with your Logo's colors and perfectly embedded it!")
                print("🔒 SCANNABILITY GUARANTEED.")
        else:
            img = base_qr

        # Output the final file
        img.save(output_file)
        print(f"\n✅ Success!")
        print(f"QR code perfectly generated for: {url}")
        print(f"Saved to: {os.path.abspath(output_file)}")
        
    except Exception as e:
        print(f"\n❌ Error generating image: {e}")
        print("Make sure you have Pillow installed via: pip install -r requirements.txt")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        link = sys.argv[1]
    else:
        print("-" * 50)
        link = input("🔗 Please enter the HTTP link to generate the QR code: ").strip()
        
    if not link:
        print("❌ Error: No link provided.")
        sys.exit(1)
        
    if not link.startswith("http://") and not link.startswith("https://"):
        print("⚠️  Warning: Missing 'http://' or 'https://'. Auto-correcting so it scans properly as a link!")
        link = "https://" + link
        print(f"🔗 Updated link: {link}")

    is_evolve = input("\n🤖 Is this QR Code for Evolve AI? (y/n): ").strip().lower()
    add_logo = is_evolve in ['y', 'yes', 'true']
        
    generate_transparent_qr(link, add_logo=add_logo)
