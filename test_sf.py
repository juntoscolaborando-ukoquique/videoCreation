import sys
import os

# Add paths to sys.path to resolve imports
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('vendor/Lingo_PERSONAS'))

from shorts_creator.image_providers.siliconflow_provider import SiliconFlowProvider

provider = SiliconFlowProvider(api_key="fake_key_123")
result = provider.generate("A cute cat", width=512, height=512, output_dir="test_out")
print("Success:", result.success)
print("Error:", result.error_message)
