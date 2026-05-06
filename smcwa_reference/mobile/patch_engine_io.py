import json
import os

file_path = '/opt/smclama/mobile/node_modules/engine.io-client/package.json'

with open(file_path, 'r') as f:
    data = json.load(f)

if 'browser' in data:
    print("Found browser field, copying to react-native...")
    data['react-native'] = data['browser']
    
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
    print("Successfully patched engine.io-client package.json")
else:
    print("Error: browser field not found in package.json")
