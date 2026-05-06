import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator, Image, Alert, ScrollView, KeyboardAvoidingView, Platform } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { Ionicons } from '@expo/vector-icons';
import { GoogleSignin, statusCodes } from '@react-native-google-signin/google-signin';
import api, { setAuthToken } from '../services/api';
import EncryptedStorage from 'react-native-encrypted-storage';

// Configure Native Google Sign-In
GoogleSignin.configure({
  webClientId: "655248995621-mf0gp9tb3omc7dfjr71kft8qr30ucjr2.apps.googleusercontent.com",
  offlineAccess: true,
  scopes: ['email', 'profile'],
});

export default function LoginScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loginSuccess, setLoginSuccess] = useState(false);
  const { signIn, setUser, isLoading, error } = useAuthStore();

  useEffect(() => {
    console.log('--- SMC Alert BUILD v1.0.29-USER-RESTORE-FIX ---');
  }, []);

  const handleGoogleLogin = async () => {
    try {
      console.log('Starting Google Login...');
      await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
      const userInfo = await GoogleSignin.signIn();
      console.log('Google Sign-In Success:', JSON.stringify(userInfo));
      
      // Handle both old and new SDK response format
      const idToken = userInfo.idToken || userInfo.data?.idToken;

      if (!idToken) {
        Alert.alert('Error', 'No ID token received from Google. Response: ' + JSON.stringify(userInfo));
        return;
      }

      // Send idToken to backend for verification (Requirement: POST /mobile/auth/google)
      const res = await api.post('/mobile/auth/google', { idToken: idToken });
      const { token: jwt, user_email, role, user_id, group_name } = res.data;
      
      await setAuthToken(jwt);
      setLoginSuccess(true);
      
      const checkPermissionsSetup = async () => {
        try {
          // Set user first so they are authenticated
          setUser({ email: user_email, role, id: user_id, group_name });
          
          const done = await EncryptedStorage.getItem('permissions_setup_done');
          if (done !== 'true') {
            // Short delay to ensure state update has finished
            setTimeout(() => {
                navigation.replace('PermissionSetup');
            }, 100);
          }
        } catch (error) {
          setUser({ email: user_email, role, id: user_id });
        }
      };

      setTimeout(() => {
        checkPermissionsSetup();
      }, 1500);
    } catch (error) {
      if (error.code === statusCodes.SIGN_IN_CANCELLED) {
        // silent - user cancelled
      } else if (error.code === statusCodes.IN_PROGRESS) {
        Alert.alert('Please wait', 'Sign in already in progress');
      } else if (error.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
        Alert.alert('Error', 'Google Play Services not available');
      } else {
        console.error('Google login failed:', error);
        Alert.alert('Sign In Error', error.message + '\nCode: ' + (error.code || 'unknown'));
      }
    }
  };

  const handleLogin = async () => {
    if (!email || !password) return;
    const userData = await signIn(email, password);
    if (userData) {
      setLoginSuccess(true);
      
      const checkPermissionsSetup = async () => {
        try {
          setUser(userData);
          const done = await EncryptedStorage.getItem('permissions_setup_done');
          if (done !== 'true') {
            setTimeout(() => {
                navigation.replace('PermissionSetup');
            }, 100);
          }
        } catch (error) {
          setUser(userData);
        }
      };

      setTimeout(() => {
        checkPermissionsSetup();
      }, 1500);
    }
  };

  if (loginSuccess) {
    return (
      <View style={styles.container}>
        <Text style={styles.success}>Login Successful!</Text>
        <ActivityIndicator size="large" color="#4CAF50" style={{ marginTop: 20 }} />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView 
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1 }}
    >
      <ScrollView 
        contentContainerStyle={styles.scrollContainer}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.logoContainer}>
          <Image 
            source={require('../../assets/logo_big.png')} 
            style={{ width: 320, height: 180 }}
            resizeMode="contain"
          />
        </View>
        <Text style={styles.title}>SMC Alert</Text>
        <Text style={styles.subtitle}>Mobile Alerting System</Text>
        
        {error && <Text style={styles.error}>{error}</Text>}
        
        <TextInput
          style={styles.input}
          placeholder="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
        />
        
        <TextInput
          style={styles.input}
          placeholder="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />
        
        <TouchableOpacity 
          style={styles.button} 
          onPress={handleLogin}
          disabled={isLoading}
        >
          {isLoading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Login</Text>
          )}
        </TouchableOpacity>

        <View style={styles.dividerContainer}>
          <View style={styles.divider} />
          <Text style={styles.dividerText}>OR</Text>
          <View style={styles.divider} />
        </View>

        <TouchableOpacity 
          style={styles.googleButton} 
          onPress={handleGoogleLogin}
          disabled={isLoading}
        >
          <Ionicons name="logo-google" size={20} color="#000" style={{ marginRight: 10 }} />
          <Text style={styles.googleButtonText}>Sign in with Google</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 20,
    backgroundColor: '#fff',
  },
  scrollContainer: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
    backgroundColor: '#fff',
    paddingBottom: 40,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: 10,
  },
  logo: {
    width: 320,
    height: 320,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    textAlign: 'center',
    color: '#007AFF',
    marginBottom: 5,
  },
  subtitle: {
    fontSize: 14,
    textAlign: 'center',
    color: '#666',
    marginBottom: 20,
  },
  input: {
    height: 50,
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    paddingHorizontal: 15,
    marginBottom: 15,
    fontSize: 16,
  },
  button: {
    height: 50,
    backgroundColor: '#007AFF',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 10,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  dividerContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 15,
  },
  divider: {
    flex: 1,
    height: 1,
    backgroundColor: '#ddd',
  },
  dividerText: {
    marginHorizontal: 10,
    color: '#888',
  },
  googleButton: {
    height: 50,
    backgroundColor: '#fff',
    borderRadius: 8,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ddd',
  },
  googleButtonText: {
    color: '#333',
    fontSize: 16,
    fontWeight: '600',
  },
  error: {
    color: 'red',
    textAlign: 'center',
    marginBottom: 10,
  },
  success: {
    color: '#4CAF50',
    fontSize: 24,
    fontWeight: 'bold',
    textAlign: 'center',
  },
});

