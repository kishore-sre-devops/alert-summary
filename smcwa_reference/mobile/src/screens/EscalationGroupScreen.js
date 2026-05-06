import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, StyleSheet, TouchableOpacity, ActivityIndicator, Alert, Modal, TextInput, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';

export default function EscalationGroupScreen() {
  const [groups, setGroups] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  
  // Form state
  const [editingGroupId, setEditingGroupId] = useState(null);
  const [groupName, setGroupName] = useState('');
  const [steps, setSteps] = useState([{ delay: 0, notify: [] }]);

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true);
      const [groupsRes, contactsRes] = await Promise.all([
        api.get('/mobile/groups'),
        api.get('/mobile/contacts')
      ]);
      setGroups(groupsRes.data);
      setContacts(contactsRes.data);
    } catch (error) {
      Alert.alert('Error', 'Failed to fetch escalation data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAddStep = () => {
    setSteps([...steps, { delay: 5, notify: [] }]);
  };

  const handleToggleContact = (stepIndex, contactId) => {
    const newSteps = [...steps];
    const notify = newSteps[stepIndex].notify;
    if (notify.includes(contactId)) {
      newSteps[stepIndex].notify = notify.filter(id => id !== contactId);
    } else {
      newSteps[stepIndex].notify = [...notify, contactId];
    }
    setSteps(newSteps);
  };

  const handleSave = async () => {
    if (!groupName) return Alert.alert('Error', 'Group Name is required');
    try {
      setIsLoading(true);
      const payload = { name: groupName, escalation_chain: steps };
      if (editingGroupId) {
        await api.put(`/mobile/groups/${editingGroupId}`, payload);
      } else {
        await api.post('/mobile/groups', payload);
      }
      setIsModalVisible(false);
      fetchData();
    } catch (e) {
      Alert.alert('Error', 'Save failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity 
        style={styles.addButton} 
        onPress={() => {
          setEditingGroupId(null);
          setGroupName('');
          setSteps([{ delay: 0, notify: [] }]);
          setIsModalVisible(true);
        }}
      >
        <Ionicons name="add" size={24} color="#fff" />
        <Text style={styles.addButtonText}>Create Escalation Group</Text>
      </TouchableOpacity>

      <FlatList
        data={groups}
        keyExtractor={item => item.id.toString()}
        renderItem={({ item }) => (
          <View style={styles.groupCard}>
            <Text style={styles.groupName}>{item.name}</Text>
            <Text style={styles.groupMeta}>{item.escalation_chain.length} Steps in Chain</Text>
            <TouchableOpacity 
              onPress={() => {
                setEditingGroupId(item.id);
                setGroupName(item.name);
                setSteps(item.escalation_chain);
                setIsModalVisible(true);
              }}
              style={styles.editBtn}
            >
              <Text style={styles.editText}>Edit Policy</Text>
            </TouchableOpacity>
          </View>
        )}
      />

      <Modal visible={isModalVisible} animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{editingGroupId ? 'Edit' : 'New'} Escalation Group</Text>
            <TouchableOpacity onPress={() => setIsModalVisible(false)}>
              <Ionicons name="close" size={28} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.form}>
            <Text style={styles.label}>Group Name (e.g. SRE Mumbai)</Text>
            <TextInput style={styles.input} value={groupName} onChangeText={setGroupName} placeholder="SRE" />

            <Text style={styles.sectionTitle}>Escalation Steps</Text>
            {steps.map((step, idx) => (
              <View key={idx} style={styles.stepBox}>
                <Text style={styles.stepTitle}>Step {idx + 1}: {idx === 0 ? 'Immediate' : `After ${step.delay} mins`}</Text>
                {idx > 0 && (
                  <TextInput 
                    style={styles.delayInput} 
                    value={String(step.delay)} 
                    keyboardType="numeric"
                    onChangeText={(val) => {
                      const newSteps = [...steps];
                      newSteps[idx].delay = parseInt(val) || 0;
                      setSteps(newSteps);
                    }}
                  />
                )}
                <Text style={styles.subLabel}>Notify Users:</Text>
                <View style={styles.contactsGrid}>
                  {contacts.map(c => (
                    <TouchableOpacity 
                      key={c.id} 
                      style={[styles.contactTag, step.notify.includes(c.id) && styles.activeTag]}
                      onPress={() => handleToggleContact(idx, c.id)}
                    >
                      <View style={{ alignItems: 'center' }}>
                        <Text style={[styles.contactText, step.notify.includes(c.id) && styles.activeText]}>
                          {c.full_name || c.email.split('@')[0]}
                        </Text>
                        {c.group_name && (
                          <Text style={{ fontSize: 9, color: step.notify.includes(c.id) ? '#fff' : '#666' }}>
                            {c.group_name}
                          </Text>
                        )}
                      </View>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            ))}

            <TouchableOpacity style={styles.addStepBtn} onPress={handleAddStep}>
              <Text style={styles.addStepText}>+ Add Escalation Level</Text>
            </TouchableOpacity>
          </ScrollView>

          <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={isLoading}>
            <Text style={styles.saveBtnText}>Save Policy</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, backgroundColor: '#f5f5f5' },
  addButton: { backgroundColor: '#007AFF', padding: 15, borderRadius: 10, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginBottom: 20 },
  addButtonText: { color: '#fff', fontWeight: 'bold', marginLeft: 10 },
  groupCard: { backgroundColor: '#fff', padding: 16, borderRadius: 12, marginBottom: 12, elevation: 2 },
  groupName: { fontSize: 18, fontWeight: 'bold' },
  groupMeta: { color: '#666', marginTop: 4 },
  editBtn: { marginTop: 10, alignSelf: 'flex-start' },
  editText: { color: '#007AFF', fontWeight: '600' },
  modalContainer: { flex: 1, backgroundColor: '#fff', padding: 20 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  modalTitle: { fontSize: 22, fontWeight: 'bold' },
  label: { fontWeight: '600', marginBottom: 8 },
  input: { backgroundColor: '#f0f0f0', padding: 12, borderRadius: 8, marginBottom: 20 },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', marginBottom: 15 },
  stepBox: { backgroundColor: '#f9f9f9', padding: 15, borderRadius: 10, marginBottom: 15, borderWidth: 1, borderColor: '#eee' },
  stepTitle: { fontWeight: 'bold', color: '#333' },
  delayInput: { width: 60, backgroundColor: '#fff', borderWidth: 1, borderColor: '#ddd', padding: 5, marginTop: 5 },
  subLabel: { fontSize: 12, color: '#888', marginTop: 10, marginBottom: 5 },
  contactsGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  contactTag: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 15, backgroundColor: '#eee', marginRight: 8, marginBottom: 8 },
  activeTag: { backgroundColor: '#007AFF' },
  contactText: { fontSize: 12 },
  activeText: { color: '#fff' },
  addStepBtn: { padding: 15, alignItems: 'center' },
  addStepText: { color: '#007AFF', fontWeight: 'bold' },
  saveBtn: { backgroundColor: '#34C759', padding: 18, borderRadius: 12, alignItems: 'center', marginTop: 10 },
  saveBtnText: { color: '#fff', fontSize: 18, fontWeight: 'bold' }
});
