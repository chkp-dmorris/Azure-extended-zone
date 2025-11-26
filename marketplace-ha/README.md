# How to deploy templates manually
To deploy the ARM templates manually without using the Azure Marketplace, follow these instructions:

1. Log in to the Microsoft Azure Portal
2. Register for the extended zone you want
   - az account set --subscription '98*********'
   - az edge-zones extended-zone register --extended-zone-name 'losangeles'
   - https://learn.microsoft.com/en-us/azure/extended-zones/request-access?tabs=powershell

3. Click "Create a resource"
4. Search for "Template deployment (deploy using custom templates)" and click "Create"
5. Click "Build your own template in the editor"
6. Load the "mainTemplate.json" file of the desired template and click "Save"
7. Enter the desired template parameters

     Must select:
    - R82- BYOL
    - VM size- Standard_D4_v4
    - Disk Type- StandardSSD_LRS
      
9. Replace the "_artifacts Location" property with:
    https://raw.githubusercontent.com/CheckPointSW/CloudGuardIaaS/master/azure/templates/
10. Select the extended zone you registered for
11. Click Purchase to deploy the solution

# Manual Deployment Steps

1. Log in to the Microsoft Azure Portal
2. Register for the extended zone you want
   - az account set --subscription '9c3f4dac-efbc-4533-acb3-7963594e6a67'
   - az edge-zones extended-zone register --extended-zone-name 'losangeles'
   - https://learn.microsoft.com/en-us/azure/extended-zones/request-access?tabs=powershell

3. Click "Create a resource"
4. Search for "Template deployment (deploy using custom templates)" and click "Create"
5. Click "Build your own template in the editor"
6. Load the "mainTemplate.json" file of the desired template and click "Save"
7. Enter the desired template parameters

     Must select:
    - R82- BYOL
    - VM size- Standard_D4_v4
    - Disk Type- StandardSSD_LRS
      
9. Replace the "_artifacts Location" property with:
    https://raw.githubusercontent.com/CheckPointSW/CloudGuardIaaS/master/azure/templates/
10. Select the extended zone you registered for
11. Click Purchase to deploy the solution

# Check Point CloudGuard Network Security High Availability for Azure

Check Point CloudGuard Network Security delivers advanced, multi-layered threat prevention to protect customer assets in Azure from malware and sophisticated threats. As a Microsoft Azure certified solution, CloudGuard Network Security enables you to easily and seamlessly secure your workloads while providing secure connectivity across your cloud and on-premises environments.

Benefits:

· Advanced threat prevention and traffic inspection

· Integrated with Azure Security Center and Azure Sentinel

· Provides consistent security policy management, enforcement, and reporting with a single pane of glass, using Check Point Unified Security Management


<a href="https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FCheckPointSW%2FCloudGuardIaaS%2Fmaster%2Fazure%2Ftemplates%2Fmarketplace-ha%2FmainTemplate.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2FCheckPointSW%2FCloudGuardIaaS%2Fmaster%2Fazure%2Ftemplates%2Fmarketplace-ha%2FcreateUiDefinition.json">
 <img src="https://aka.ms/deploytoazurebutton" alt="Deploy to Azure" />
</a>


To deploy with full control over all the template options use: [Full Control Deployment](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FCheckPointSW%2FCloudGuardIaaS%2Fmaster%2Fazure%2Ftemplates%2Fmarketplace-ha%2FmainTemplate.json)


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
