const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'node_modules', 'engine.io-client', 'package.json');

try {
  if (fs.existsSync(filePath)) {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    if (data.browser) {
      console.log('Patching engine.io-client: Copying browser field to react-native');
      data['react-native'] = data.browser;
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
      console.log('Success!');
    } else {
      console.log('Warning: No browser field found in engine.io-client package.json');
    }
  } else {
    console.log('Error: engine.io-client package.json not found at', filePath);
  }
} catch (e) {
  console.error('Error patching engine.io-client:', e);
  process.exit(1);
}
