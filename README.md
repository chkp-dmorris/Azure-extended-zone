# How to deploy templates manually
To deploy the ARM templates manually without using the Azure Marketplace, follow these instructions:

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
    - VM size- Standard_D4_v4
    - Disk Type- StandardSSD_LRS
      
8. Replace the "_artifacts Location" property with:
    https://raw.githubusercontent.com/CheckPointSW/CloudGuardIaaS/master/azure/templates/
9. Select the extended zone you registered for
10. Click Purchase to deploy the solution
