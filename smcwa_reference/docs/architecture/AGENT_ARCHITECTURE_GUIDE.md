# Agent Architecture Guide

## Overview
This document explains the supported operating systems and architectures for SMC-LAMA agents, with proper naming conventions and detailed descriptions.

## Architecture Naming Conventions

### Windows
- **x64 (64-bit)**: Standard 64-bit Windows (Intel/AMD processors)
  - Also known as: AMD64, x86-64, x86_64
  - Most common architecture for Windows
  - Supports: Windows 10/11, Windows Server 2016+
  
- **ARM64**: Windows on ARM
  - Qualcomm Snapdragon processors
  - Surface Pro X, Windows 11 ARM devices
  - Note: x86 (32-bit) is NOT supported

### Linux
- **x64 (AMD64)**: Intel/AMD 64-bit processors
  - Most common Linux architecture
  - Supports: Ubuntu, Debian, CentOS, RHEL, Amazon Linux
  
- **ARM64**: ARM 64-bit processors
  - Raspberry Pi 4+, AWS Graviton, ARM-based servers
  - Also known as: aarch64

### macOS
- **Intel (x64)**: Intel-based Macs
  - Macs from 2019 and earlier
  - Intel Core processors
  
- **Apple Silicon (ARM64)**: Apple's M-series processors
  - M1, M2, M3, and newer
  - Native ARM64 architecture

### Docker
- **AMD64**: Standard x64 Docker containers
  - Most common Docker architecture
  - Works on x64 hosts
  
- **ARM64**: ARM-based Docker containers
  - Raspberry Pi, AWS Graviton, ARM servers
  - Multi-architecture Docker images

### ECS Fargate
- **AMD64**: Standard x64 ECS Fargate tasks
  - Default architecture for most AWS workloads
  
- **ARM64**: ARM-based ECS Fargate tasks
  - AWS Graviton processors
  - Cost-effective option for compatible workloads

## UI Display

The Agent Onboarding page now shows:

1. **OS-specific architecture names**:
   - Windows: "x64 (64-bit)" and "ARM64" (not "AMD64")
   - Linux: "x64 (AMD64)" and "ARM64"
   - macOS: "Intel (x64)" and "Apple Silicon"
   - Docker/ECS: "AMD64" and "ARM64"

2. **Detailed descriptions** for each architecture:
   - What processors it supports
   - Common use cases
   - Platform-specific notes

3. **OS information**:
   - Supported OS versions
   - Platform-specific requirements

## Backend Architecture Normalization

The backend API automatically normalizes architecture names:

- `x64` → `amd64` (for Windows compatibility)
- `aarch64` → `arm64` (standardization)
- `arm64` → `arm64` (unchanged)

This allows the UI to display user-friendly names (like "x64") while the backend uses standard names (like "amd64").

## Supported Architectures Summary

| OS | Architecture | Display Name | Backend Name | Notes |
|---|---|---|---|---|
| Windows | 64-bit | x64 (64-bit) | amd64 | Most common |
| Windows | ARM | ARM64 | arm64 | Windows on ARM |
| Linux | 64-bit | x64 (AMD64) | amd64 | Most common |
| Linux | ARM | ARM64 | arm64 | Raspberry Pi, Graviton |
| macOS | Intel | Intel (x64) | amd64 | Pre-2020 Macs |
| macOS | Apple Silicon | Apple Silicon | arm64 | M1/M2/M3 |
| Docker | x64 | AMD64 | amd64 | Standard containers |
| Docker | ARM | ARM64 | arm64 | ARM containers |
| ECS Fargate | x64 | AMD64 | amd64 | Standard tasks |
| ECS Fargate | ARM | ARM64 | arm64 | Graviton tasks |

## Not Supported

- **x86 (32-bit)**: Not supported for any OS
- **ARMv7 (32-bit ARM)**: Not supported
- **Other architectures**: Only x64/AMD64 and ARM64 are supported

## How to Choose the Right Architecture

### Windows
1. Check your Windows version: Settings → System → About
2. Look for "System type":
   - "64-bit operating system, x64-based processor" → Choose **x64 (64-bit)**
   - "64-bit operating system, ARM-based processor" → Choose **ARM64**

### Linux
1. Run: `uname -m`
   - `x86_64` → Choose **x64 (AMD64)**
   - `aarch64` or `arm64` → Choose **ARM64**

### macOS
1. Click Apple menu → About This Mac
2. Look for "Chip":
   - "Intel" → Choose **Intel (x64)**
   - "Apple M1/M2/M3" → Choose **Apple Silicon**

### Docker
1. Check your host architecture: `docker version`
2. Or check container: `docker run --rm alpine uname -m`
   - `x86_64` → Choose **AMD64**
   - `aarch64` → Choose **ARM64**

### ECS Fargate
1. Check your task definition CPU architecture
2. Standard tasks → Choose **AMD64**
3. Graviton tasks → Choose **ARM64**

## Technical Details

### Architecture Detection
The agent automatically detects the system architecture at runtime and reports it to the server. This helps verify that the correct agent was downloaded.

### Compatibility
- **x64/AMD64**: Fully compatible across all supported OSes
- **ARM64**: Native on ARM systems, emulated on some x64 systems (not recommended)

### Performance
- Using the correct architecture ensures optimal performance
- Using wrong architecture may cause:
  - Slower execution (emulation)
  - Compatibility issues
  - Missing features

## UI Improvements

The updated Agent Onboarding page now includes:

1. ✅ **Clear architecture labels** with OS-specific naming
2. ✅ **Descriptive text** explaining each architecture
3. ✅ **OS version information** for each platform
4. ✅ **Visual organization** with cards for each OS type
5. ✅ **Environment indicator** showing PROD or UAT

## Example Display

```
Linux
Ubuntu, Debian, CentOS, RHEL, Amazon Linux, and other Linux distributions

[x64 (AMD64)]  [ARM64]
Intel/AMD 64-bit processors  ARM 64-bit processors
(most common)                 (Raspberry Pi, AWS Graviton)
```

This makes it much clearer which architecture to choose for each operating system!

