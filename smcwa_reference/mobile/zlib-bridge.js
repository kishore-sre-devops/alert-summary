// SMC LAMA: Hardened Zlib Bridge
console.log('🚀 SMC LAMA: Zlib Bridge Loading...');

const constants = {
  Z_NO_FLUSH: 0,
  Z_PARTIAL_FLUSH: 1,
  Z_SYNC_FLUSH: 2,
  Z_FULL_FLUSH: 3,
  Z_FINISH: 4,
  Z_BLOCK: 5,
  Z_OK: 0,
  Z_STREAM_END: 1,
  Z_NEED_DICT: 2,
  Z_ERRNO: -1,
  Z_STREAM_ERROR: -2,
  Z_DATA_ERROR: -3,
  Z_MEM_ERROR: -4,
  Z_BUF_ERROR: -5,
  Z_VERSION_ERROR: -6,
  Z_DEFAULT_COMPRESSION: -1,
  Z_FILTERED: 1,
  Z_HUFFMAN_ONLY: 2,
  Z_RLE: 3,
  Z_FIXED: 4,
  Z_DEFAULT_STRATEGY: 0,
  DEFLATE: 1,
  INFLATE: 2,
  GZIP: 3,
  GUNZIP: 4,
  DEFLATERAW: 5,
  INFLATERAW: 6,
  UNZIP: 7,
};

let zlibModule = Object.assign({}, constants);

try {
  const browserifyZlib = require('browserify-zlib');
  zlibModule = Object.assign(zlibModule, browserifyZlib, constants);
  console.log('🚀 SMC LAMA: browserify-zlib loaded successfully');
} catch (e) {
  console.log('⚠️ SMC LAMA: browserify-zlib failed, using constants-only fallback. Error:', e.message);
}

// Ensure all constants are on the module AND in a constants sub-object
Object.assign(zlibModule, constants);
zlibModule.constants = constants;

// Attach to global as backup
global.zlib = zlibModule;

console.log('🚀 SMC LAMA: Zlib Bridge Active, Z_SYNC_FLUSH=' + zlibModule.Z_SYNC_FLUSH);

module.exports = zlibModule;
