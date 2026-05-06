import { Audio } from 'expo-av';
import { Platform } from 'react-native';

class AlertCallManager {
  constructor() {
    this.soundObject = null;
    this.isPlaying = false;
  }

  async setupAudioMode() {
    try {
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        staysActiveInBackground: true, // Keep playing if app goes background
        interruptionModeIOS: (Audio.INTERRUPTION_MODE_IOS_DUCK_OTHERS || 2), // Duck other audio
        playsInSilentModeIOS: true, // Crucial: Play even if switch is silent
        shouldDuckAndroid: true,
        interruptionModeAndroid: (Audio.INTERRUPTION_MODE_ANDROID_DUCK_OTHERS || 2),
        playThroughEarpieceAndroid: false, // Use speaker
      });
      console.log('Audio mode configured for high priority alerts');
    } catch (error) {
      console.error('Failed to set audio mode:', error);
    }
  }

  async playAlertSound(audioUri, token = null) {
    if (this.isPlaying) {
      console.log('Already playing alert sound');
      return;
    }

    try {
      await this.setupAudioMode();

      console.log(`Loading alert sound from: ${audioUri}`);
      
      const source = { uri: audioUri };
      if (token) {
        source.headers = { Authorization: `Bearer ${token}` };
      }

      const { sound } = await Audio.Sound.createAsync(
        source,
        { shouldPlay: true, isLooping: true, volume: 1.0 }
      );

      this.soundObject = sound;
      this.isPlaying = true;
      
      // Ensure it starts playing immediately
      await sound.playAsync();
      console.log('Alert sound playing...');

    } catch (error) {
      console.error('Failed to load/play alert sound:', error);
      this.isPlaying = false;
    }
  }

  async stopRinging() {
    if (this.soundObject) {
      try {
        await this.soundObject.stopAsync();
        await this.soundObject.unloadAsync();
      } catch (error) {
        console.warn('Error stopping sound:', error);
      }
      this.soundObject = null;
    }
    this.isPlaying = false;
    console.log('Alert sound stopped');
  }
}

export default new AlertCallManager();
