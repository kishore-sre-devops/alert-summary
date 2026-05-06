// Stub for CallService - RNCallKeep removed due to fatal crashes
class CallService {
  constructor() {
    this.isInitialized = false;
    this.currentCallId = null;
  }

  async setup() {
    this.isInitialized = true;
    console.log('CallService stub initialized');
  }

  displayIncomingCall(uuid, handle, localizedCallerName = 'Critical Alert') {
    console.log(`CallService stub: Displaying call (Simulated): ${uuid}`);
    this.currentCallId = uuid;
  }

  endCall(uuid) {
    console.log('CallService stub: End call');
    this.currentCallId = null;
  }
  
  reportEndCallWithUUID(uuid, reason) {
      // No-op
  }
}

export default new CallService();
