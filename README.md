# Azure Extended Zones + CloudGuard

## Introduction
Organizations are moving latency-sensitive applications closer to end users. Azure Extended Zones extend Azure’s global infrastructure with small-footprint metro sites that keep workloads close while preserving the same operational model as the parent region. Official docs: https://learn.microsoft.com/azure/extended-zones/

## What Are Azure Extended Zones?
Extended Zones are metro or industry-specific Azure sites attached to a parent region. They use the same ARM, RBAC, identity, and policy model, while running compute, disks, and network paths locally for ultra-low latency.

## Benefits
- Ultra-low latency for edge workloads
- Local data processing for data residency
- Better UX for real-time and interactive apps

## Architecture (Data vs Control Plane)
- **Data plane (local):** VMs, disks, network paths
- **Control plane (parent region):** ARM, RBAC, identity, policies
This keeps performance local while management stays consistent.

## Why Secure Extended Zones?
- Broader attack surface from distributed edge workloads
- Latency constraints make backhauling traffic undesirable
- Compliance may require local inspection/logging
Deploy security directly inside the Extended Zone where the workload runs.

## CloudGuard in Extended Zones
1) Deploy CloudGuard Security Gateways directly in the Extended Zone
2) Inline threat prevention at the edge (IPS, App Control, URLF, IA, zero-trust segmentation)
3) Unified visibility/management via Smart-1 Cloud or on-prem Security Management Server

## What You Can Deploy
- Single Gateway
- Single-Zone Cluster (HA in one Extended Zone)
- Custom multi-gateway builds using these templates
Supports Extended-Zone-compatible SKUs (e.g., `Standard_D4_v4` with `StandardSSD_LRS`).

# Example Deployment (Azure Extended Zone)

1. Log in and set the subscription
   ```sh
   az login
   az account set --subscription "<subscription-id>"
   ```

2. Register the Extended Zone you plan to use (examples below)
   ```sh
   # Los Angeles (parent region: West US)
   az edge-zones extended-zone register --extended-zone-name losangeles

   # Perth (parent region: Australia East)
   az edge-zones extended-zone register --extended-zone-name perth
   ```

3. Deploy CloudGuard from the Azure Portal using the UI-enabled templates
   - High Availability (HA) Cluster: [Deploy to Azure](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fchkp-dmorris%2FAzure-extended-zone%2Frefs%2Fheads%2Fmain%2Fmarketplace-ha%2FmainTemplate.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fchkp-dmorris%2FAzure-extended-zone%2Frefs%2Fheads%2Fmain%2Fmarketplace-ha%2FcreateUiDefinition.json)
   - Single Gateway: [Deploy to Azure](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fchkp-dmorris%2FAzure-extended-zone%2Frefs%2Fheads%2Fmain%2Fmarketplace-single%2FmainTemplate.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fchkp-dmorris%2FAzure-extended-zone%2Frefs%2Fheads%2Fmain%2Fmarketplace-single%2FcreateUiDefinition.json)

   If you manually paste `mainTemplate.json` into the portal editor, set `_artifactsLocation` to:
   `https://raw.githubusercontent.com/chkp-dmorris/Azure-extended-zone/main/`

4. Important: choose only supported VM size and disk types for Extended Zones
   - Recommended for Extended Zones: `Standard_D4_v4`
   - Disk type: `StandardSSD_LRS` (or `Premium_SSD` where available)
   - Selecting unsupported SKUs will fail validation/provisioning; check Azure Extended Zone SKU availability for your target region.

5. Region/zone pairing rules
   - `losangeles` requires region `West US`
   - `perth` requires region `Australia East`

Repository: https://github.com/chkp-dmorris/Azure-extended-zone

# Cluster File Replacement Instructions (Azure)

To update the cluster members with the latest Azure scripts (`azure_ha_test.py` and `azure_had.py`):

1. **SFTP the two files to each unit.**

2. **Back up the existing files:**
   ```sh
   cp $FWDIR/scripts/azure_had.py $FWDIR/scripts/azure_had.py_backup
   cp $FWDIR/scripts/azure_ha_test.py $FWDIR/scripts/azure_ha_test.py_backup
   ```

3. **Copy the new files over and rename them:**
   ```sh
   cp azure_had.py $FWDIR/scripts/azure_had.py
   cp azure_ha_test.py $FWDIR/scripts/azure_ha_test.py
   ```

4. **Change the permissions to -r-xr-x--- (550):**
   ```sh
   chmod 550 $FWDIR/scripts/azure_had.py
   chmod 550 $FWDIR/scripts/azure_ha_test.py
   ```

5. **Confirm the permissions and files:**
   ```sh
   ls -la $FWDIR/scripts/azure_had.py
   ls -la $FWDIR/scripts/azure_ha_test.py
   ```

6. **Test and confirm the changes worked:**
   - Run:
     ```sh
     $FWDIR/scripts/azure_ha_test.py
     ```
   - Check logs:
     ```sh
     tail /opt/CPsuite-R82/fw1/log/azure_had.elg
     tail -f /opt/CPsuite-R82/fw1/log/azure_had.elg
     ```
   - Test failover and monitor the log.
