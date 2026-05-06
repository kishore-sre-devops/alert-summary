import React, { useState, useEffect, useCallback } from 'react';
import { 
  View, 
  Text, 
  FlatList, 
  StyleSheet, 
  TouchableOpacity, 
  ActivityIndicator, 
  Alert, 
  Modal, 
  TextInput, 
  ScrollView,
  Switch
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { useAuthStore } from '../store/authStore';

export default function UserManagementScreen() {
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  
  // Form state
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [isActive, setIsActive] = useState(true);
  
  const fetchUsers = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await api.get('/users/');
      setUsers(response.data);
    } catch (error) {
      console.error('Fetch users failed:', error);
      Alert.alert('Error', 'Failed to fetch users');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleOpenModal = (user = null) => {
    if (user) {
      setEditingUser(user);
      setFullName(user.full_name || '');
      setEmail(user.email || '');
      setMobile(user.mobile || '');
      setPassword(''); // Password remains empty for edit
      setRole(user.role || 'user');
      setIsActive(user.is_active !== false);
    } else {
      setEditingUser(null);
      setFullName('');
      setEmail('');
      setMobile('');
      setPassword('');
      setRole('user');
      setIsActive(true);
    }
    setIsModalVisible(true);
  };

  const handleSaveUser = async () => {
    if ((!email && !mobile) || (!editingUser && !password)) {
      Alert.alert('Validation', 'Email or Mobile is required, and Password is required for new users.');
      return;
    }

    try {
      setIsLoading(true);
      const userData = {
        full_name: fullName,
        email: email || null,
        mobile: mobile || null,
        role: role,
        is_active: isActive,
      };

      if (password) {
        userData.password = password;
      }

      if (editingUser) {
        await api.put(`/users/${editingUser.id}`, userData);
        Alert.alert('Success', 'User updated successfully');
      } else {
        await api.post('/users/', userData);
        Alert.alert('Success', 'User created successfully');
      }
      
      setIsModalVisible(false);
      fetchUsers();
    } catch (error) {
      console.error('Save user failed:', error);
      const errorMsg = error.response?.data?.detail || 'Failed to save user';
      Alert.alert('Error', errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteUser = (userId) => {
    Alert.alert(
      'Confirm Delete',
      'Are you sure you want to delete this user?',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Delete', 
          style: 'destructive',
          onPress: async () => {
            try {
              setIsLoading(true);
              await api.delete(`/users/${userId}`);
              fetchUsers();
            } catch (error) {
              Alert.alert('Error', 'Failed to delete user');
            } finally {
              setIsLoading(false);
            }
          }
        }
      ]
    );
  };

  const renderUserItem = ({ item }) => (
    <View style={styles.userCard}>
      <View style={styles.userInfo}>
        <View style={styles.nameRow}>
          <Text style={styles.userName}>{item.full_name || 'No Name'}</Text>
          <View style={[
            styles.statusDot, 
            { backgroundColor: item.is_active ? '#34C759' : '#FF3B30' }
          ]} />
        </View>
        <Text style={styles.userDetails}>{item.email || item.mobile}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <View style={styles.roleContainer}>
            <Text style={styles.roleTag}>{item.role.toUpperCase()}</Text>
          </View>
          {item.group_name && (
            <View style={[styles.roleContainer, { backgroundColor: '#E3F2FD', marginLeft: 8 }]}>
              <Text style={[styles.roleTag, { color: '#007AFF' }]}>{item.group_name.toUpperCase()}</Text>
            </View>
          )}
        </View>
      </View>
      <View style={styles.actions}>
        <TouchableOpacity style={styles.actionButton} onPress={() => handleOpenModal(item)}>
          <Ionicons name="create-outline" size={24} color="#007AFF" />
        </TouchableOpacity>
        <TouchableOpacity style={styles.actionButton} onPress={() => handleDeleteUser(item.id)}>
          <Ionicons name="trash-outline" size={24} color="#FF3B30" />
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={users}
        renderItem={renderUserItem}
        keyExtractor={item => item.id.toString()}
        refreshing={isLoading}
        onRefresh={fetchUsers}
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <TouchableOpacity style={styles.addButton} onPress={() => handleOpenModal()}>
            <Ionicons name="add" size={24} color="#fff" />
            <Text style={{ color: '#fff', fontWeight: 'bold', marginLeft: 8 }}>Add New User</Text>
          </TouchableOpacity>
        }
        ListEmptyComponent={
          !isLoading && <Text style={styles.emptyText}>No users found</Text>
        }
      />


      <Modal
        visible={isModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setIsModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {editingUser ? 'Edit User' : 'Add New User'}
              </Text>
              <TouchableOpacity onPress={() => setIsModalVisible(false)}>
                <Ionicons name="close" size={24} color="#333" />
              </TouchableOpacity>
            </View>
            
            <ScrollView style={styles.form}>
              <Text style={styles.label}>Full Name</Text>
              <TextInput
                style={styles.input}
                value={fullName}
                onChangeText={setFullName}
                placeholder="John Doe"
              />
              
              <Text style={styles.label}>Email</Text>
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                placeholder="email@example.com"
                autoCapitalize="none"
                keyboardType="email-address"
              />
              
              <Text style={styles.label}>Mobile</Text>
              <TextInput
                style={styles.input}
                value={mobile}
                onChangeText={setMobile}
                placeholder="+919999999999"
                keyboardType="phone-pad"
              />
              
              <Text style={styles.label}>{editingUser ? 'New Password (Optional)' : 'Password'}</Text>
              <TextInput
                style={styles.input}
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                placeholder="••••••••"
              />
              
              <Text style={styles.label}>Role</Text>
              <View style={styles.rolePicker}>
                {[
                  { label: 'Admin', value: 'admin' },
                  { label: 'Operator', value: 'operator' },
                  { label: 'Viewer', value: 'user' }
                ].map((r) => (
                  <TouchableOpacity
                    key={r.value}
                    style={[
                      styles.roleOption,
                      role === r.value && styles.roleOptionActive
                    ]}
                    onPress={() => setRole(r.value)}
                  >
                    <Text style={[
                      styles.roleOptionText,
                      role === r.value && styles.roleOptionTextActive
                    ]}>
                      {r.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={styles.toggleContainer}>
                <Text style={styles.label}>Active Status</Text>
                <Switch
                  value={isActive}
                  onValueChange={setIsActive}
                  trackColor={{ false: '#767577', true: '#34C759' }}
                  thumbColor={isActive ? '#fff' : '#f4f3f4'}
                />
              </View>
            </ScrollView>
            
            <TouchableOpacity 
              style={styles.saveButton} 
              onPress={handleSaveUser}
              disabled={isLoading}
            >
              {isLoading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.saveButtonText}>Save User</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  addButton: {
    backgroundColor: '#007AFF',
    padding: 12,
    borderRadius: 8,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  list: {
    padding: 16,
  },
  userCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  userInfo: {
    flex: 1,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginLeft: 8,
  },
  userName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#000',
  },
  userDetails: {
    fontSize: 14,
    color: '#8E8E93',
    marginTop: 2,
  },
  roleContainer: {
    marginTop: 8,
    alignSelf: 'flex-start',
    backgroundColor: '#E5E5EA',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  roleTag: {
    fontSize: 12,
    fontWeight: '600',
    color: '#3A3A3C',
  },
  actions: {
    flexDirection: 'row',
  },
  actionButton: {
    marginLeft: 16,
    padding: 4,
  },
  emptyText: {
    textAlign: 'center',
    marginTop: 50,
    fontSize: 16,
    color: '#8E8E93',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    height: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
  },
  form: {
    flex: 1,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#3A3A3C',
    marginBottom: 8,
    marginTop: 16,
  },
  toggleContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 8,
    paddingRight: 8,
  },
  input: {
    backgroundColor: '#F2F2F7',
    borderRadius: 10,
    padding: 12,
    fontSize: 16,
  },
  rolePicker: {
    flexDirection: 'row',
    marginTop: 8,
    marginBottom: 20,
  },
  roleOption: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: '#F2F2F7',
    marginHorizontal: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  roleOptionActive: {
    backgroundColor: '#E3F2FD',
    borderColor: '#007AFF',
  },
  roleOptionText: {
    fontSize: 14,
    color: '#3A3A3C',
  },
  roleOptionTextActive: {
    color: '#007AFF',
    fontWeight: '600',
  },
  saveButton: {
    backgroundColor: '#007AFF',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginTop: 20,
  },
  saveButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
});
