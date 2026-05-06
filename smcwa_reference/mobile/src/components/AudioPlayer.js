import React, { useEffect, useState } from 'react';
import { View, TouchableOpacity, Text, StyleSheet } from 'react-native';
import { Audio } from 'expo-av';
import { getAuthToken } from '../services/api';
import Constants from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';

const BASE_URL = Constants.expoConfig?.extra?.apiUrl || 'http://10.0.2.2:8000/api/v1';

export default function AudioPlayer({ alertId }) {
  const [sound, setSound] = useState();
  const [isPlaying, setIsPlaying] = useState(false);
  const [loading, setLoading] = useState(false);

  async function playSound() {
    try {
      setLoading(true);
      const token = await getAuthToken();
      
      const { sound: newSound } = await Audio.Sound.createAsync(
         { 
             uri: `${BASE_URL}/mobile/alerts/${alertId}/audio`,
             headers: { Authorization: `Bearer ${token}` }
         },
         { shouldPlay: true }
      );
      
      setSound(newSound);
      setIsPlaying(true);
      setLoading(false);
      
      newSound.setOnPlaybackStatusUpdate((status) => {
          if (status.didJustFinish) {
              setIsPlaying(false);
          }
      });

    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  }

  async function stopSound() {
     if (sound) {
         await sound.stopAsync();
         setIsPlaying(false);
     }
  }

  useEffect(() => {
    return () => {
      if (sound) {
        sound.unloadAsync();
      }
    };
  }, [sound]);

  return (
    <View style={styles.container}>
      <TouchableOpacity 
        style={styles.button} 
        onPress={isPlaying ? stopSound : playSound}
        disabled={loading}
      >
        <Ionicons name={isPlaying ? "pause" : "play"} size={24} color="#007AFF" />
        <Text style={styles.text}>
            {loading ? "Loading..." : isPlaying ? "Stop TTS" : "Play TTS"}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginVertical: 10,
  },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    backgroundColor: '#e3f2fd',
    borderRadius: 8,
    alignSelf: 'flex-start',
  },
  text: {
    marginLeft: 8,
    color: '#007AFF',
    fontWeight: '600',
  }
});
