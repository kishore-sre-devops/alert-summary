import React from 'react';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createDrawerNavigator } from '@react-navigation/drawer';
import LoginScreen from '../screens/LoginScreen';
import AlertFeedScreen from '../screens/AlertFeedScreen';
import ProfileScreen from '../screens/ProfileScreen';
import AlertDetailScreen from '../screens/AlertDetailScreen';
import UserManagementScreen from '../screens/UserManagementScreen';
import EscalationGroupScreen from '../screens/EscalationGroupScreen';
import IncomingAlertScreen from '../screens/IncomingAlertScreen';
import PermissionSetupScreen from '../screens/PermissionSetupScreen';
import { useAuthStore } from '../store/authStore';
import { useAlertStore } from '../store/alertStore';
import { Ionicons } from '@expo/vector-icons';
import { View, ActivityIndicator, Image, Text } from 'react-native';

import axios from 'axios';
import EncryptedStorage from 'react-native-encrypted-storage';

const Stack = createStackNavigator();
const Tab = createBottomTabNavigator();
const Drawer = createDrawerNavigator();

function TabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName;

          if (route.name === 'Alerts') {
            iconName = focused ? 'notifications' : 'notifications-outline';
          } else if (route.name === 'Profile') {
            iconName = focused ? 'person' : 'person-outline';
          }

          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: '#007AFF',
        tabBarInactiveTintColor: 'gray',
        headerShown: false,
      })}
    >
      <Tab.Screen name="Alerts" component={AlertFeedScreen} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

function MainDrawerNavigator() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  return (
    <Drawer.Navigator
      screenOptions={{
        drawerActiveTintColor: '#007AFF',
        drawerLabelStyle: {
          marginLeft: -20,
        },
        headerTitle: () => (
          <Image 
            source={require('../../assets/logo_header.png')} 
            style={{ width: 200, height: 60 }}
            resizeMode="contain"
          />
        ),
        headerTitleAlign: 'center',
        headerStyle: {
          height: 100,
        },
      }}
    >
      <Drawer.Screen 
        name="Home" 
        component={TabNavigator} 
        options={{
          title: 'SMC Lama Alerts',
          drawerIcon: ({ color }) => (
            <Ionicons name="home-outline" size={22} color={color} />
          ),
        }}
      />
      
      {isAdmin && (
        <>
          <Drawer.Screen 
            name="Users" 
            component={UserManagementScreen} 
            options={{
              title: 'User Management',
              drawerIcon: ({ color }) => (
                <Ionicons name="people-outline" size={22} color={color} />
              ),
            }}
          />
          <Drawer.Screen 
            name="EscalationGroups" 
            component={EscalationGroupScreen} 
            options={{
              title: 'Escalation Groups',
              drawerIcon: ({ color }) => (
                <Ionicons name="git-network-outline" size={22} color={color} />
              ),
            }}
          />
        </>
      )}
    </Drawer.Navigator>
  );
}

export default function AppNavigator() {
  const { user, isLoading } = useAuthStore();
  const { incomingCall } = useAlertStore();
  const [initialRoute, setInitialRoute] = React.useState(null);

  React.useEffect(() => {
    const determineInitialRoute = async () => {
      try {
        const token = await EncryptedStorage.getItem('userToken');
        if (!token) {
          setInitialRoute('Login');
          return;
        }
        const permsDone = await EncryptedStorage.getItem('permissions_setup_done');
        if (permsDone !== 'true') {
          setInitialRoute('PermissionSetup');
        } else {
          setInitialRoute('Main');
        }
      } catch (error) {
        setInitialRoute('Login');
      }
    };
    if (!isLoading) {
        determineInitialRoute();
    }
  }, [isLoading]);

  if (isLoading || !initialRoute) {
      return (
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#1a237e' }}>
              <Text style={{ color: 'white', fontSize: 18, marginBottom: 20 }}>SMC LAMA</Text>
              <ActivityIndicator size="large" color="#fff" />
          </View>
      );
  }

  return (
    <Stack.Navigator initialRouteName={initialRoute}>
      {user ? (
        <>
          {/* Always include the Main stack and AlertDetail */}
          <Stack.Screen 
            name="Main" 
            component={MainDrawerNavigator} 
            options={{ headerShown: false }} 
          />
          <Stack.Screen 
            name="AlertDetail" 
            component={AlertDetailScreen} 
            options={{ title: 'Alert Details' }}
          />
          <Stack.Screen 
            name="PermissionSetup" 
            component={PermissionSetupScreen} 
            options={{ headerShown: false }} 
          />
          
          {/* Add IncomingAlert as a full-screen modal over the stack when it exists */}
          {incomingCall && (
            <Stack.Screen 
              name="IncomingAlert" 
              component={IncomingAlertScreen} 
              options={{ 
                headerShown: false, 
                animationEnabled: false,
                presentation: 'fullScreenModal'
              }} 
            />
          )}
        </>
      ) : (
        <Stack.Screen 
            name="Login" 
            component={LoginScreen} 
            options={{ headerShown: false }} 
        />
      )}
    </Stack.Navigator>
  );
}
