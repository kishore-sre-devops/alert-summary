import React from 'react';
import { Box, Typography, Button } from '@mui/material';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.href = '/servers';
  };

  render() {
    if (this.state.hasError) {
      return (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100vh',
            p: 3,
            bgcolor: '#f5f5f5',
          }}
        >
          <Typography variant="h4" sx={{ mb: 2, color: 'error.main' }}>
            Something went wrong
          </Typography>
          <Typography variant="body1" sx={{ mb: 3, color: 'text.secondary', textAlign: 'center' }}>
            {this.state.error?.message || 'An unexpected error occurred'}
          </Typography>
          <Button variant="contained" onClick={this.handleReset}>
            Go to Servers
          </Button>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;

