import React from 'react';
import { Box, Typography } from '@mui/material';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

const CircularGauge = ({ value = 0, label = 'Health', max = 100, color = '#4CAF50' }) => {
  const percentage = Math.min((value / max) * 100, 100);
  
  const data = [
    { name: 'Used', value: percentage },
    { name: 'Remaining', value: 100 - percentage }
  ];

  const getColor = () => {
    if (percentage >= 80) return '#4CAF50'; // Green
    if (percentage >= 50) return '#FF9800'; // Orange
    return '#F44336'; // Red
  };

  const displayColor = color === 'auto' ? getColor() : color;

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
        backgroundColor: '#f5f5f5',
        borderRadius: 2,
        minHeight: 200,
      }}
    >
      <ResponsiveContainer width="100%" height={150}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            startAngle={180}
            endAngle={0}
            innerRadius={50}
            outerRadius={70}
            dataKey="value"
            stroke="none"
          >
            <Cell fill={displayColor} />
            <Cell fill="#e0e0e0" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <Typography variant="h6" sx={{ mt: 2, fontWeight: 'bold' }}>
        {percentage.toFixed(0)}%
      </Typography>
      <Typography variant="body2" sx={{ color: '#666' }}>
        {label}
      </Typography>
    </Box>
  );
};

export default CircularGauge;
