# How to deploy templates manually
To deploy the ARM templates manually without using the Azure Marketplace, follow these instructions:

1. Log in to the Microsoft Azure Portal
2. Register for the extended zone you want
   - az account set --subscription '00000000-0000-0000-0000-000000000000'
   - az edge-zones extended-zone register --extended-zone-name losangeles
   - az edge-zones extended-zone register --extended-zone-name perth
   - https://learn.microsoft.com/en-us/azure/extended-zones/request-access?tabs=powershell

3. Click "Create a resource"
4. Search for "Template deployment (deploy using custom templates)" and click "Create"
5. Click "Build your own template in the editor"
6. Load the "mainTemplate.json" file of the desired template and click "Save"

7. Select the extended zone you registered for:
   - If you select 'losangeles' as the extended zone, you must select 'West US' as the region.
   - If you select 'perth' as the extended zone, you must select 'Australia East' as the region.

8. Enter the desired template parameters

    Must select:
   - VM size- Standard_D4_v4
   - Disk Type- StandardSSD_LRS
      
9. Replace the "_artifacts Location" property with:
   https://raw.githubusercontent.com/chkp-dmorris/Azure-extended-zone/main/
10. Click Purchase to deploy the solution

# How to Use

Choose the Template:

- Use `marketplace-single/mainTemplate.json` for a single gateway deployment in an existing or new VNet.
- Use `marketplace-ha/mainTemplate.json` for a high availability (HA) cluster deployment in an existing or new VNet.

Refer to the template parameters for customization options (VNet, subnets, VM size, disk type, extended zone, etc).

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
