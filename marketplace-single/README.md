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

# Check Point CloudGuard Network Security Single Gateway for Azure

Check Point CloudGuard Network Security delivers advanced, multi-layered threat prevention to protect customer assets in Azure from malware and sophisticated threats. As a Microsoft Azure certified solution, CloudGuard Network Security enables you to easily and seamlessly secure your workloads while providing secure connectivity across your cloud and on-premises environments.

Benefits:

· Advanced threat prevention and traffic inspection

· Provides consistent security policy management, enforcement, and reporting with a single pane of glass, using Check Point Unified Security Management


<a href="https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fchkp-dmorris%2FAzure-extended-zone%2Frefs%2Fheads%2Fmain%2Fmarketplace-single%2FmainTemplate.json/createUIDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2Fchkp-dmorris%2FAzure-extended-zone%2Frefs%2Fheads%2Fmain%2Fmarketplace-single%2FcreateUiDefinition.json">
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
