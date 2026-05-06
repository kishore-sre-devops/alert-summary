#!/bin/bash
cd /opt/smclama/mobile
docker run --rm -v /opt/smclama/mobile:/app smclama-mobile-builder:latest > /opt/smclama/mobile/build_log_v1.0.48_b33.txt 2>&1
