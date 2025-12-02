# Manual Deployment Steps

1. Log in to the Microsoft Azure Portal
2. Register for the extended zone you want
  - az account set --subscription '<YOUR_SUBSCRIPTION_ID>'
  - az edge-zones extended-zone register --extended-zone-name 'losangeles'
  - https://learn.microsoft.com/en-us/azure/extended-zones/request-access?tabs=powershell

3. Click "Create a resource"
4. Search for "Template deployment (deploy using custom templates)" and click "Create"
5. Click "Build your own template in the editor"
6. Load the `marketplace-single/mainTemplate.json` file and click "Save"

7. Select the extended zone you registered for:
  - If you select 'losangeles' as the extended zone, you must select 'West US' as the region.
  - If you select 'perth' as the extended zone, you must select 'Australia East' as the region.

8. Enter the desired template parameters

   Must select:
  - R81.20 or R82 - BYOL/PAYG
  - VM size - Standard_D4_v4
  - Disk Type - StandardSSD_LRS
      
9. Replace the "_artifacts Location" property with:
  https://raw.githubusercontent.com/CheckPointSW/CloudGuardIaaS/master/azure/templates/
10. Click Purchase to deploy the solution

# Check Point CloudGuard Network Security Single Gateway for Azure

Check Point CloudGuard Network Security delivers advanced, multi-layered threat prevention to protect customer assets in Azure from malware and sophisticated threats. As a Microsoft Azure certified solution, CloudGuard Network Security enables you to easily and seamlessly secure your workloads while providing secure connectivity across your cloud and on-premises environments.

Benefits:

· Advanced threat prevention and traffic inspection

· Provides consistent security policy management, enforcement, and reporting with a single pane of glass, using Check Point Unified Security Management


<a href="https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fchkp-dmorris%2FAzure-extended-zone%2Frefs%2Fheads%2Fmain%2Fmarketplace-single%2FmainTemplate.json">
 <img src="https://aka.ms/deploytoazurebutton" alt="Deploy to Azure" />
</a>


To deploy with full control over all the template options use: [Full Control Deployment](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FCheckPointSW%2FCloudGuardIaaS%2Fmaster%2Fazure%2Ftemplates%2Fmarketplace-single%2FmainTemplate.json)


## Notes
- When `vnetNewOrExisting='new'` and `extendedZone!='None'`, the template uses the Extended Zone VNet nested template.
- Tags per resource can be supplied via `tagsByResource`.
- For PAYG plans, `plan` is set automatically based on `cloudGuardVersion`.

## Reference
- Check Point Support Article: Enhancing Cloud Security with Check Point CloudGuard in Azure Extended Zones (SK184335)
  https://support.checkpoint.com/results/sk/sk184335
