const fs = require('fs');
const path = require('path');

const libraries = [
  'engine.io-client',
  'socket.io-client',
  'ws'
];

libraries.forEach(lib => {
  const pkgPath = path.join(__dirname, 'node_modules', lib, 'package.json');
  try {
    if (fs.existsSync(pkgPath)) {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
      
      if (pkg.exports) {
        console.log(`REMOVING exports field from ${lib} to force browser resolution...`);
        delete pkg.exports;
        fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2));
        console.log(`Successfully patched ${lib}!`);
      } else {
        console.log(`${lib} already patched or no exports field.`);
      }
    }
  } catch (e) {
    console.error(`Failed to patch ${lib}:`, e);
  }
});
