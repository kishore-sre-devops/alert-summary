const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

config.resolver.extraNodeModules = {
  ...config.resolver.extraNodeModules,
  'zlib': require.resolve('./zlib-bridge.js'),
  'stream': require.resolve('readable-stream'),
};

config.resolver.resolverMainFields = ['react-native', 'browser', 'main'];

module.exports = config;
