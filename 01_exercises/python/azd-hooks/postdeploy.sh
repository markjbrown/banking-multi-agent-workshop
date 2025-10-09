#!/bin/bash
# Bash wrapper for PowerShell postdeploy script
pwsh -File "$(dirname "$0")/postdeploy.ps1" "$@"