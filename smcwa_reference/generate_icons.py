from PIL import Image
import os

def create_adaptive_icon(source_path, output_path, size=500, logo_size=300):
    # Open the source logo
    logo = Image.open(source_path).convert("RGBA")
    
    # Resize the logo to fit in the safe zone
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
    
    # Create a transparent background
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    
    # Calculate position to center the logo
    offset = ((size - logo.size[0]) // 2, (size - logo.size[1]) // 2)
    
    # Paste the logo onto the canvas
    canvas.paste(logo, offset, logo)
    
    # Save the result
    canvas.save(output_path)
    print(f"Adaptive icon created at {output_path} ({size}x{size}, logo is {logo.size[0]}x{logo.size[1]})")

def create_square_icon(source_path, output_path, size=1024, logo_size=800):
    logo = Image.open(source_path).convert("RGBA")
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
    
    # Square icon usually has a background color or is just the logo
    # For iOS/Store, we'll use a white background
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    offset = ((size - logo.size[0]) // 2, (size - logo.size[1]) // 2)
    canvas.paste(logo, offset, logo)
    canvas.save(output_path)
    print(f"Standard icon created at {output_path} ({size}x{size})")

if __name__ == "__main__":
    source = "/opt/smclama/ui/assets/logo-smc.png"
    
    # Create adaptive icon (with padding for Android)
    create_adaptive_icon(source, "/opt/smclama/mobile/assets/adaptive-icon.png")
    
    # Create standard icon
    create_square_icon(source, "/opt/smclama/mobile/assets/icon.png")
