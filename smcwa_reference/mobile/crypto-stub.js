module.exports = {
  randomBytes: () => { throw new Error('crypto.randomBytes() is not supported in this environment'); },
};
