import sys
import os
sys.path.insert(0, '/root/a_VIDEO_GENERATION/VideoLingo/Lingo')
from shorts_creator.footage_generator_v2 import FootageGeneratorV2
gen = FootageGeneratorV2(output_dir='/tmp')
try:
    print("Testing pollinations...")
    path = gen.generate_image("A futuristic city")
    print(f"Success: {path}")
except Exception as e:
    print(f"Failed: {e}")
