import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useAuthStore } from '../store/authStore';
import Constants from 'expo-constants';

export default function ProfileScreen() {
  const { user, signOut } = useAuthStore();
  const version = Constants.expoConfig?.version || '1.0.52';

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.label}>Email</Text>
        <Text style={styles.value}>{user?.email}</Text>
        
        <Text style={styles.label}>Role</Text>
        <Text style={styles.value}>{user?.role || 'User'}</Text>

        {user?.group_name && (
          <>
            <Text style={styles.label}>Group</Text>
            <Text style={styles.value}>{user.group_name}</Text>
          </>
        )}

        <Text style={styles.label}>App Version</Text>
        <Text style={styles.value}>v{version}</Text>
      </View>

      <TouchableOpacity style={styles.logoutButton} onPress={signOut}>
        <Text style={styles.logoutText}>Logout</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: '#f5f5f5',
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 20,
    marginBottom: 20,
    elevation: 2,
  },
  label: {
    fontSize: 14,
    color: '#888',
    marginBottom: 5,
  },
  value: {
    fontSize: 18,
    color: '#333',
    marginBottom: 15,
  },
  logoutButton: {
    backgroundColor: '#ff4444',
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
  },
  logoutText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 16,
  }
});
