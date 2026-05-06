import React, { useEffect, useState, useCallback } from 'react';
import { View, FlatList, StyleSheet, RefreshControl, Text, TouchableOpacity } from 'react-native';
import { useAlertStore } from '../store/alertStore';
import AlertCard from '../components/AlertCard';

export default function AlertFeedScreen({ navigation }) {
  const { alerts, isLoading, fetchAlerts } = useAlertStore();
  const [activeTab, setActiveTab] = useState('active');

  const loadData = useCallback(() => {
    fetchAlerts(activeTab);
  }, [activeTab, fetchAlerts]);

  useEffect(() => {
    loadData();
    
    // Poll every 30 seconds for real-time auto-resolve (Requirement 4)
    const interval = setInterval(() => {
      fetchAlerts(activeTab);
    }, 30000);

    return () => clearInterval(interval);
  }, [activeTab, fetchAlerts, loadData]);

  const renderItem = ({ item }) => (
    <AlertCard 
      alert={item} 
      onPress={() => navigation.navigate('AlertDetail', { alert: item })}
    />
  );

  return (
    <View style={styles.container}>
      <View style={styles.tabContainer}>
        <TouchableOpacity 
          style={[styles.tab, activeTab === 'active' && styles.activeTab]} 
          onPress={() => setActiveTab('active')}
        >
          <Text style={[styles.tabText, activeTab === 'active' && styles.activeTabText]}>Active</Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={[styles.tab, activeTab === 'history' && styles.activeTab]} 
          onPress={() => setActiveTab('history')}
        >
          <Text style={[styles.tabText, activeTab === 'history' && styles.activeTabText]}>History</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={alerts}
        renderItem={renderItem}
        keyExtractor={(item, index) => (item.id ? item.id.toString() : index.toString())}
        refreshControl={
          <RefreshControl refreshing={isLoading} onRefresh={loadData} />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            {activeTab === 'active' ? (
              <View style={styles.allClear}>
                <Text style={styles.allClearIcon}>✅</Text>
                <Text style={styles.allClearText}>All Clear - No Active Alerts</Text>
              </View>
            ) : (
              <Text style={styles.emptyText}>No history found</Text>
            )}
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 5,
  },
  activeTab: {
    backgroundColor: '#007AFF',
  },
  tabText: {
    fontSize: 16,
    color: '#666',
    fontWeight: '600',
  },
  activeTabText: {
    color: '#fff',
  },
  list: {
    padding: 10,
  },
  empty: {
    padding: 20,
    alignItems: 'center',
    marginTop: 100,
  },
  emptyText: {
    color: '#888',
    fontSize: 16,
  },
  allClear: {
    alignItems: 'center',
  },
  allClearIcon: {
    fontSize: 60,
    marginBottom: 20,
  },
  allClearText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#2e7d32',
  }
});
