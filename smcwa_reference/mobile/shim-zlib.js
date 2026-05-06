// SMC LAMA: Definitive Zlib/Node Shim
import { Platform } from 'react-native';

if (typeof Buffer === 'undefined') {
  global.Buffer = require('buffer').Buffer;
}

if (typeof process === 'undefined') {
  global.process = require('process');
}
global.process.browser = true;

try {
  // CRITICAL: require 'zlib' which should hit our Metro alias
  const zlibShim = require('zlib');
  
  const Z_SYNC_FLUSH = 2;
  const Z_FULL_FLUSH = 3;
  const Z_NO_FLUSH = 0;

  // Reinforced properties
  const constObj = {
    Z_SYNC_FLUSH: 2,
    Z_FULL_FLUSH: 3,
    Z_NO_FLUSH: 0,
    Z_FINISH: 4,
    Z_BLOCK: 5,
    Z_OK: 0,
    Z_STREAM_END: 1,
    Z_NEED_DICT: 2,
  };

  zlibShim.Z_SYNC_FLUSH = Z_SYNC_FLUSH;
  zlibShim.Z_FULL_FLUSH = Z_FULL_FLUSH;
  zlibShim.Z_NO_FLUSH = Z_NO_FLUSH;
  zlibShim.constants = Object.assign(zlibShim.constants || {}, constObj);

  // Set global variables
  global.zlib = zlibShim;
  global.Z_SYNC_FLUSH = Z_SYNC_FLUSH;
  global.Z_FULL_FLUSH = Z_FULL_FLUSH;
  global.Z_NO_FLUSH = Z_NO_FLUSH;

  console.log('✅ SMC LAMA: Zlib Shim Reinforced via Bridge (Z_SYNC_FLUSH=' + zlibShim.Z_SYNC_FLUSH + ')');
} catch (e) {
  console.log('❌ SMC LAMA: Shim Failure', e.message);
  
  // Absolute Emergency Fallback
  const fallback = {
    Z_SYNC_FLUSH: 2,
    Z_FULL_FLUSH: 3,
    Z_NO_FLUSH: 0,
    deflate: () => {},
    inflate: () => {},
  };
  global.zlib = fallback;
  global.Z_SYNC_FLUSH = 2;
}
