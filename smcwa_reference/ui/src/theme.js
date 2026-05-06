import { createTheme } from '@mui/material/styles';
const SMC_GREEN = '#7BB241';
const theme = createTheme({
  palette: {
    primary: { main: SMC_GREEN },
    background: { default: '#f6f8fb' }
  },
  components: {
    MuiAppBar: { styleOverrides: { root: { backgroundColor: '#ffffff', color: '#333' } } }
  }
});
export default theme;
